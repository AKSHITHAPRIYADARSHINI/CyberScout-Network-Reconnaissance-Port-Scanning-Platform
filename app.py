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

app = Flask(__name__, template_folder='.')

# ============================================
# ROUTE 1: Serve the HTML page
# ============================================
@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')

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
        result = subprocess.check_output(
            nmap_cmd,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=300  # 5 minute timeout
        )

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
        print("[!] ERROR: Scan timed out (exceeded 5 minutes)")
        return jsonify({'error': 'Scan timed out (exceeded 5 minutes)'}), 500
    
    except subprocess.CalledProcessError as e:
        print(f"[!] ERROR: Nmap command failed: {str(e)}")
        return jsonify({'error': f'Nmap error: {str(e)}'}), 500
    
    except Exception as e:
        print(f"[!] ERROR: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# ============================================
# HELPER FUNCTION: Build Nmap Command
# ============================================
def build_nmap_command(target, scan_type, custom_command):
    """
    Build Nmap command based on scan type
    Returns list of command arguments for subprocess
    """
    
    # Validate target (basic CIDR/IP validation)
    if not is_valid_target(target):
        raise ValueError(f"Invalid target format: {target}")

    # If custom command provided, use it
    if scan_type == 'custom' and custom_command:
        # Parse custom command and add target
        cmd_parts = custom_command.split()
        # Remove 'nmap' if it's at the start
        if cmd_parts[0].lower() == 'nmap':
            cmd_parts = cmd_parts[1:]
        # Remove target if already in command
        cmd_parts = [p for p in cmd_parts if p != target]
        # Build final command
        nmap_cmd = ['sudo', 'nmap'] + cmd_parts + [target, '-oX', '-']
        return nmap_cmd

    # Build command based on scan type
    base_cmd = ['sudo', 'nmap']

    if scan_type == 'fast':
        # Fast scan - 100 most common ports
        nmap_cmd = base_cmd + ['-F', target, '-oX', '-']
    
    elif scan_type == 'standard':
        # Standard scan - all ports
        nmap_cmd = base_cmd + ['-p-', target, '-oX', '-']
    
    elif scan_type == 'version':
        # Service version detection
        nmap_cmd = base_cmd + ['-sV', target, '-oX', '-']
    
    elif scan_type == 'os':
        # OS detection
        nmap_cmd = base_cmd + ['-O', target, '-oX', '-']
    
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
    """
    # IP regex pattern
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    cidr_pattern = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'
    
    if re.match(ip_pattern, target) or re.match(cidr_pattern, target):
        return True
    
    # Check for comma-separated IPs
    if ',' in target:
        parts = target.split(',')
        return all(re.match(ip_pattern, p.strip()) for p in parts)
    
    # Check for IP range
    if '-' in target:
        parts = target.split('-')
        if len(parts) == 2:
            return re.match(ip_pattern, parts[0].strip()) and re.match(ip_pattern, parts[1].strip())
    
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
                        print(f"        [+] Open port {port_num}/{protocol}: {service_name}")
            
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
    
    # Start Flask server
    app.run(
        debug=True,
        host='127.0.0.1',
        port=5000,
        use_reloader=False
    )