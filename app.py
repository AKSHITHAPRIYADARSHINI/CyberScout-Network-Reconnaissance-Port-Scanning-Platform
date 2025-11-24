#!/usr/bin/env python3
# ============================================
# CYBERSCOUT FLASK BACKEND - ADVANCED VERSION
# Real Nmap Integration with Custom Commands
# ============================================

from flask import Flask, render_template, request, jsonify
import subprocess
import xml.etree.ElementTree as ET
import json
import os
import re
import sys

app = Flask(__name__, template_folder='.')

# ============================================
# CONFIGURATION
# ============================================
# Available ports if 5000 is taken
AVAILABLE_PORTS = [5000, 5001, 5002, 5003, 5004, 8000, 8080]
DEFAULT_PORT = 5000

# ============================================
# ROUTE 1: Serve the HTML page
# ============================================
@app.route('/')
def index():
    """Serve the main UI page"""
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"[!] Error loading template: {str(e)}")
        return jsonify({'error': 'Failed to load UI'}), 500

# ============================================
# ROUTE 2: API endpoint for scanning
# ============================================
@app.route('/api/scan', methods=['POST'])
def scan():
    """
    This function runs Nmap with custom or predefined commands
    Receives: { "target": "192.168.1.0/24", "scanType": "fast", "customCommand": "..." }
    Returns: { "status": "success", "hosts": [...] }
    """
    try:
        # Get request data
        data = request.get_json()
        target = data.get('target')
        scan_type = data.get('scanType', 'fast')
        custom_command = data.get('customCommand', '')

        if not target:
            return jsonify({'error': 'No target provided'}), 400

        print(f"\n[*] ================================================")
        print(f"[*] SCANNING TARGET: {target}")
        print(f"[*] SCAN TYPE: {scan_type}")
        print(f"[*] ================================================\n")

        # Build Nmap command based on scan type
        nmap_cmd = build_nmap_command(target, scan_type, custom_command)
        
        print(f"[*] Running command: {' '.join(nmap_cmd)}\n")

        # Execute Nmap
        try:
            result = subprocess.check_output(
                nmap_cmd,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300  # 5 minute timeout
            )
        except subprocess.CalledProcessError as e:
            print(f"[!] Nmap execution failed with output:\n{e.output}")
            raise

        print(f"[*] Nmap output received, parsing results...\n")

        # Parse Nmap XML output
        hosts_data = parse_nmap_xml(result)

        print(f"[*] Found {len(hosts_data)} hosts\n")
        print(f"[*] ================================================\n")

        return jsonify({
            'status': 'success',
            'hosts': hosts_data,
            'target': target,
            'count': len(hosts_data),
            'command': ' '.join(nmap_cmd)
        })

    except subprocess.TimeoutExpired:
        error_msg = 'Scan timed out (exceeded 5 minutes)'
        print(f"[!] ERROR: {error_msg}")
        return jsonify({'error': error_msg}), 500
    
    except subprocess.CalledProcessError as e:
        error_msg = f'Nmap command failed: {str(e)}'
        print(f"[!] ERROR: {error_msg}")
        return jsonify({'error': error_msg}), 500
    
    except ValueError as e:
        error_msg = f'Invalid input: {str(e)}'
        print(f"[!] ERROR: {error_msg}")
        return jsonify({'error': error_msg}), 400
    
    except Exception as e:
        error_msg = f'Server error: {str(e)}'
        print(f"[!] ERROR: {error_msg}")
        return jsonify({'error': error_msg}), 500

# ============================================
# HELPER FUNCTION: Build Nmap Command
# ============================================
def build_nmap_command(target, scan_type, custom_command):
    """
    Build Nmap command based on scan type
    Returns list of command arguments for subprocess
    
    Supports:
    - Fast scan (100 ports)
    - Standard scan (all ports)
    - Version detection
    - OS detection
    - Aggressive scan
    - Custom commands
    """
    
    # Validate target (basic CIDR/IP validation)
    if not is_valid_target(target):
        raise ValueError(f"Invalid target format: {target}")

    # If custom command provided, use it
    if scan_type == 'custom' and custom_command:
        # Parse custom command and add target
        cmd_parts = custom_command.split()
        
        # Remove 'nmap' if it's at the start
        if cmd_parts and cmd_parts[0].lower() == 'nmap':
            cmd_parts = cmd_parts[1:]
        
        # Remove target if already in command
        cmd_parts = [p for p in cmd_parts if p != target]
        
        # Build final command with sudo
        nmap_cmd = ['sudo', 'nmap'] + cmd_parts + [target, '-oX', '-']
        return nmap_cmd

    # Build command based on scan type
    base_cmd = ['sudo', 'nmap']

    if scan_type == 'fast':
        # Fast scan - 100 most common ports
        nmap_cmd = base_cmd + ['-F', target, '-oX', '-']
    
    elif scan_type == 'standard':
        # Standard scan - all ports (slow!)
        nmap_cmd = base_cmd + ['-p-', target, '-oX', '-']
    
    elif scan_type == 'version':
        # Service version detection
        nmap_cmd = base_cmd + ['-sV', '-F', target, '-oX', '-']
    
    elif scan_type == 'os':
        # OS detection
        nmap_cmd = base_cmd + ['-O', '-F', target, '-oX', '-']
    
    elif scan_type == 'aggressive':
        # Aggressive scan - full information
        nmap_cmd = base_cmd + ['-A', target, '-oX', '-']
    
    else:
        # Default to fast scan
        nmap_cmd = base_cmd + ['-F', '-sV', '-O', target, '-oX', '-']

    return nmap_cmd

# ============================================
# HELPER FUNCTION: Validate Target
# ============================================
def is_valid_target(target):
    """
    Validate target is proper IP/CIDR format
    Returns True if valid, False otherwise
    
    Supports:
    - Single IP: 192.168.1.1
    - CIDR: 192.168.1.0/24
    - Range: 192.168.1.1-10
    - List: 192.168.1.1,192.168.1.2
    """
    
    # IP regex pattern (simple but effective)
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    cidr_pattern = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'
    
    # Check single IP
    if re.match(ip_pattern, target):
        return True
    
    # Check CIDR notation
    if re.match(cidr_pattern, target):
        return True
    
    # Check for comma-separated IPs
    if ',' in target:
        parts = target.split(',')
        return all(re.match(ip_pattern, p.strip()) for p in parts)
    
    # Check for IP range
    if '-' in target:
        parts = target.split('-')
        if len(parts) == 2:
            return (re.match(ip_pattern, parts[0].strip()) and 
                    re.match(ip_pattern, parts[1].strip()))
    
    return False

# ============================================
# HELPER FUNCTION: Parse Nmap XML Output
# ============================================
def parse_nmap_xml(xml_output):
    """
    Parse Nmap XML output and extract host information
    
    Extracts:
    - IP Address
    - Status (up/down)
    - Open Ports
    - Service Names & Versions
    - Operating System
    - MAC Address
    - Response Time (Latency)
    """
    try:
        root = ET.fromstring(xml_output)
        hosts = []

        # Iterate through each host in XML
        for host in root.findall('host'):
            # ======== EXTRACT IP ADDRESS ========
            ip_elem = host.find("address[@addrtype='ipv4']")
            if ip_elem is None:
                continue
            
            ip = ip_elem.get('addr')
            print(f"    [+] Found host: {ip}")
            
            # ======== EXTRACT STATUS ========
            status_elem = host.find('status')
            status = status_elem.get('state') if status_elem is not None else 'unknown'
            
            # ======== EXTRACT OPEN PORTS ========
            ports = []
            ports_elem = host.find('ports')
            if ports_elem is not None:
                for port_elem in ports_elem.findall('port'):
                    port_num = port_elem.get('portid')
                    protocol = port_elem.get('protocol')
                    
                    # Get port state
                    state_elem = port_elem.find('state')
                    port_state = state_elem.get('state') if state_elem is not None else 'unknown'
                    
                    # Get service info
                    service_elem = port_elem.find('service')
                    service_name = service_elem.get('name') if service_elem is not None else 'unknown'
                    service_version = service_elem.get('version') if service_elem is not None else ''
                    
                    # Only include OPEN ports
                    if port_state == 'open':
                        port_info = {
                            'port': port_num,
                            'protocol': protocol,
                            'service': service_name,
                            'version': service_version,
                            'state': port_state
                        }
                        ports.append(port_info)
                        version_str = f" ({service_version})" if service_version else ""
                        print(f"        [+] Open port {port_num}/{protocol}: {service_name}{version_str}")
            
            # ======== EXTRACT OS INFO ========
            os_info = 'Unknown'
            os_elem = host.find('os/osmatch')
            if os_elem is not None:
                os_info = os_elem.get('name', 'Unknown')
            
            # ======== EXTRACT MAC ADDRESS ========
            mac = 'N/A'
            mac_elem = host.find("address[@addrtype='mac']")
            if mac_elem is not None:
                mac = mac_elem.get('addr')
            
            # ======== EXTRACT RESPONSE TIME ========
            latency = '0ms'
            uptime_elem = host.find('uptime')
            if uptime_elem is not None:
                seconds = uptime_elem.get('seconds')
                if seconds:
                    latency = f"{int(seconds)/1000:.2f}s"
            
            # ======== CREATE HOST OBJECT ========
            host_obj = {
                'ip': ip,
                'status': status,
                'os': os_info,
                'mac': mac,
                'ports': ports,
                'latency': latency,
                'port_count': len(ports)
            }
            
            hosts.append(host_obj)

        return hosts

    except ET.ParseError as e:
        print(f"[!] XML Parse Error: {str(e)}")
        print(f"[!] XML Output (first 500 chars): {xml_output[:500]}")
        return []
    except Exception as e:
        print(f"[!] Error parsing XML: {str(e)}")
        return []

# ============================================
# ERROR HANDLERS
# ============================================
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

# ============================================
# HEALTH CHECK ENDPOINT
# ============================================
@app.route('/api/health', methods=['GET'])
def health():
    """Simple health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'CyberScout',
        'version': '2.0-advanced'
    })

# ============================================
# NMAP INFO ENDPOINT
# ============================================
@app.route('/api/nmap-info', methods=['GET'])
def nmap_info():
    """Get Nmap version info"""
    try:
        result = subprocess.check_output(
            ['nmap', '--version'],
            text=True,
            timeout=5
        )
        return jsonify({
            'status': 'available',
            'info': result.strip()
        })
    except Exception as e:
        return jsonify({
            'status': 'unavailable',
            'error': 'Nmap not found or not installed'
        }), 500

# ============================================
# MAIN ENTRY POINT
# ============================================
if __name__ == '__main__':
    print("\n")
    print("╔════════════════════════════════════════════════════════╗")
    print("║         🛡️  CYBERSCOUT BACKEND STARTING  🛡️           ║")
    print("║              ADVANCED VERSION - Custom Nmap            ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()
    print("📍 Access UI at: http://localhost:5000")
    print()
    print("⚠️  IMPORTANT LEGAL NOTICE:")
    print("   This tool scans ONLY networks you own or have")
    print("   explicit permission to scan.")
    print()
    print("❌ UNAUTHORIZED NETWORK SCANNING IS ILLEGAL")
    print("   Violators face serious criminal penalties.")
    print()
    print("✅ AUTHORIZED USES:")
    print("   - Your own home/office network")
    print("   - Corporate networks with written permission")
    print("   - Approved penetration testing engagements")
    print("   - Isolated lab/test networks")
    print()
    print("════════════════════════════════════════════════════════")
    print()
    print("AVAILABLE SCAN TYPES:")
    print("  🚀 Fast Scan (-F) - 100 most common ports")
    print("  ⚡ Standard (-p-) - All 65,535 ports")
    print("  📦 Version Detection (-sV) - Service versions")
    print("  🖥️  OS Detection (-O) - Operating system")
    print("  ⚔️  Aggressive (-A) - Full scan")
    print("  🔧 Custom - Your own Nmap command")
    print()
    
    # Check if Nmap is available
    try:
        nmap_version = subprocess.check_output(['nmap', '--version'], text=True)
        version_parts = nmap_version.split()
        print("✅ Nmap is installed:")
        print(f"   {nmap_version.strip()}")
    except FileNotFoundError:
        print("❌ WARNING: Nmap is NOT installed!")
        print("   Install with: sudo apt install nmap -y (Linux/Kali)")
        print("   Or download from: https://nmap.org/download.html (Windows)")
    except Exception as e:
        print(f"⚠️  Could not verify Nmap: {str(e)}")
    
    print()
    print("════════════════════════════════════════════════════════")
    print()
    
    # Try to start Flask server
    try:
        # Try to start on default port
        print(f"[*] Starting Flask server on port {DEFAULT_PORT}...")
        app.run(
            debug=True,
            host='127.0.0.1',
            port=DEFAULT_PORT,
            use_reloader=False
        )
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n⚠️  Port {DEFAULT_PORT} is already in use!")
            print("Trying alternative ports...\n")
            
            # Try alternative ports
            port_found = False
            for alt_port in AVAILABLE_PORTS[1:]:
                try:
                    print(f"[*] Trying port {alt_port}...")
                    print(f"[*] Access UI at: http://localhost:{alt_port}")
                    print()
                    app.run(
                        debug=True,
                        host='127.0.0.1',
                        port=alt_port,
                        use_reloader=False
                    )
                    port_found = True
                    break
                except OSError:
                    continue
            
            if not port_found:
                print("\n❌ All ports are in use!")
                print("\nPlease kill existing Flask processes:")
                print("   Linux/Kali: sudo pkill -f 'python.*app'")
                print("   Or: sudo lsof -i :5000 && sudo kill -9 [PID]")
                sys.exit(1)
        else:
            raise