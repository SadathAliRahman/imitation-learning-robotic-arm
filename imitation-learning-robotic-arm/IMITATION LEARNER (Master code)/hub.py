import socket
import serial
import time
import threading
import concurrent.futures
from ping3 import ping
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ SYSTEM STATE & SETTINGS
# ==========================================
target_ip = None
target_port = 5005
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
esp_serial = None

sys_state = {
    "connection": "wifi", 
    "mode": "wifi_ui_rec",
    "is_playing": False,
    "speed_delay": 25  # Default safe movement delay (ms per degree)
}

saved_moves = []
current_cobot_payload = None 

# 🤖 Connect to myCobot
COBOT_PORT = '/dev/ttyAMA0'
try:
    from pymycobot.mycobot import MyCobot
    mc = MyCobot(COBOT_PORT, 1000000)
    mc.release_all_servos()
    cobot_available = True
    print("✅ myCobot connected.")
except Exception as e:
    mc = None
    cobot_available = False
    print("⚠️ myCobot not found on PI.")

# ==========================================
# 📡 NETWORK SCANNER
# ==========================================
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_ip(ip):
    if ping(ip, timeout=0.2):
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            if hostname.endswith('.local'): hostname = hostname[:-6]
        except Exception:
            hostname = "Unknown Device"
        return {"ip": ip, "name": hostname}
    return None

def scan_network():
    my_ip = get_local_ip()
    if my_ip == '127.0.0.1': return []
    network_prefix = ".".join(my_ip.split('.')[:-1])
    active_devices = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        ips_to_check = [f"{network_prefix}.{i}" for i in range(1, 255)]
        results = executor.map(check_ip, ips_to_check)
        for result in results:
            if result: active_devices.append(result)
    return active_devices

# ==========================================
# 🔄 CORE ROUTING & MATH
# ==========================================
def send_to_esp(payload_str):
    if sys_state["is_playing"]: return
    
    # We now append the 7th parameter (speed_delay) before sending!
    final_payload = f"{payload_str},{int(sys_state['speed_delay'])}"
    
    if sys_state["connection"] == "wifi" and target_ip:
        try:
            udp_socket.sendto(final_payload.encode('utf-8'), (target_ip, target_port))
        except: pass
    elif sys_state["connection"] == "wired" and esp_serial:
        try:
            esp_serial.write(f"{final_payload}\n".encode('utf-8'))
        except: pass

def map_angle(val, in_min, in_max, out_min, out_max):
    mapped = (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return max(min(int(mapped), out_max), out_min)

def cobot_thread():
    global current_cobot_payload
    while True:
        if cobot_available and "cobot" in sys_state["mode"] and not sys_state["is_playing"]:
            angles = mc.get_angles()
            if angles and len(angles) >= 5:
                # Map -90 to +90 over to standard 0 to 180
                base     = map_angle(angles[0], -90, 90, 0, 180)
                shoulder = map_angle(angles[1], -90, 90, 0, 180)
                elbow    = map_angle(angles[2], -90, 90, 0, 180)
                w_pitch  = map_angle(angles[3], -90, 90, 0, 180)
                w_roll   = map_angle(angles[4], -90, 90, 0, 180)
                
                # We save only the 6 angles here. Speed is appended inside send_to_esp
                payload_str = f"{base},{shoulder},{elbow},{w_pitch},{w_roll},0"
                current_cobot_payload = payload_str 
                send_to_esp(payload_str)
                
        time.sleep(0.05)

threading.Thread(target=cobot_thread, daemon=True).start()

# ==========================================
# 🌐 WEB DASHBOARD
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dynamic Arm Hub</title>
    <style>
        body { background-color: #121212; color: #fff; font-family: sans-serif; text-align: center; padding: 20px;}
        .panel { position: relative; background: #1e1e1e; padding: 25px; border-radius: 12px; margin-bottom: 20px; max-width: 600px; margin: 0 auto 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.4);}
        input[type=text], select { width: 80%; padding: 12px; border-radius: 6px; border: none; background: #333; color: #0f0; text-align: center; margin-bottom: 15px; font-size: 1rem;}
        button { padding: 12px 20px; font-size: 1rem; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; color: white; width: 100%; margin-top: 5px;}
        
        .btn-blue { background-color: #2196F3; } .btn-green { background-color: #4caf50; } 
        .btn-red { background-color: #f44336; } .btn-purple { background-color: #9c27b0; } 
        .btn-gray { background-color: #555; } .btn-gold { background-color: #FFC107; color: black;}
        .btn-back { position: absolute; top: 20px; right: 20px; background: #333; color: #fff; border: 1px solid #555; width: auto; padding: 6px 12px; font-size: 0.9rem; margin: 0; }
        .btn-back:hover { background: #f44336; border-color: #f44336; }
        
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .grid-4 { display: grid; grid-template-columns: 1fr; gap: 10px; }
        .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;}
        .slider-box { background: #2a2a2a; padding: 10px; border-radius: 8px; }
        input[type=range] { width: 100%; }
        #status-bar { color: #0f0; margin-top: 15px; font-family: monospace; background: #000; padding: 10px; border-radius: 5px;}
        .hidden { display: none !important; }
        .settings-row { display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 10px;}
        .settings-row input { width: 100%; margin-top: 8px;}
    </style>
</head>
<body>
    <h2>🤖 Advanced Master Hub</h2>
    
    <div class="panel" id="step1">
        <h3>Step 1: Locate Arm</h3>
        <div class="grid-2" style="margin-bottom: 15px;">
            <button class="btn-gray" onclick="runScan()" id="scan-btn">🔍 Scan Network</button>
            <button class="btn-blue" onclick="locateArm()">📡 Connect</button>
        </div>
        <select id="device_list" class="hidden" onchange="updateIpField()"><option value="">Select a device...</option></select>
        <input type="text" id="target_ip" placeholder="Scan or Enter IP (e.g., 192.168.4.1)">
    </div>

    <div class="panel hidden" id="step2">
        <button class="btn-back" onclick="goBack(1)">↩ Back</button>
        <h3>Step 2: Select Mode</h3>
        <div class="grid-4">
            <button class="btn-purple" onclick="setMode('wifi_cobot_live')">1. Wireless: Cobot Real-Time Mirror</button>
            <button class="btn-purple" onclick="setMode('wifi_cobot_rec')">2. Wireless: Cobot Record Checkpoints</button>
            <button class="btn-purple" onclick="setMode('wifi_ui_rec')">3. Wireless: Web UI Record & Play</button>
            <button class="btn-red" onclick="showWiredSetup()">4. Wired: Web UI Record & Play</button>
        </div>
        
        <div id="wired-setup" class="hidden" style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #444;">
            <p>1. Connect USB Cable now.<br>2. Enter COM Port (e.g., COM13):</p>
            <input type="text" id="com_port" value="COM13">
            <button class="btn-gold" onclick="setMode('wired_ui_rec')">Confirm USB Link & Start</button>
        </div>
    </div>

    <div class="panel hidden" id="step3">
        <button class="btn-back" onclick="goBack(2)">↩ Back</button>
        <h3 id="active-mode-title">Control Panel</h3>
        
        <div style="background: #111; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <div class="settings-row">
                <label>🏎️ Robot Movement Speed: <span id="spd_val" style="color:#FFC107">Normal (25ms)</span></label>
                <input type="range" min="5" max="45" step="1" value="25" dir="rtl" onchange="updateSettings('speed_delay', this.value)">
                <small style="color:#aaa; margin-top:5px; font-size:0.8rem;">Controls the physical safety delay on the ESP32 servos.</small>
            </div>
        </div>

        <div id="cobot-panel" class="hidden">
            <p style="color:#00e676; font-weight:bold;">🟢 Live Mirroring Active</p>
            <div class="grid-2" style="margin-bottom: 15px;">
                <button class="btn-gray" onclick="cobotPower('unlock')">🔓 Unlock Motors</button>
                <button class="btn-gold" onclick="cobotPower('lock')">🔒 Lock Motors</button>
            </div>
            
            <div id="cobot-rec-section" class="hidden">
                <button class="btn-blue" onclick="action('record_cobot')">📍 Save Checkpoint</button>
            </div>
        </div>

        <div id="ui-panel" class="hidden">
            <div class="controls" id="sliders"></div>
            <button class="btn-blue" onclick="action('record_ui')">📍 Snap Waypoint</button>
        </div>
        
        <div id="playback-panel" class="hidden">
            <hr style="border-color:#333; margin: 20px 0;">
            <p>Memory: <span id="mem_count" style="color:#ffeb3b; font-weight:bold;">0 Frames</span></p>
            <div class="grid-2">
                <button class="btn-green" onclick="action('play')">▶️ Play Memory</button>
                <button class="btn-red" onclick="action('clear')">🗑️ Clear</button>
            </div>
        </div>
    </div>

    <div id="status-bar">Awaiting initialization...</div>

    <script>
        const joints = [{n: "Base", v: 90}, {n: "Shoulder", v: 112}, {n: "Elbow", v: 68}, {n: "Wrist P", v: 90}, {n: "Wrist R", v: 90}, {n: "Gripper", v: 0}];
        let currentAngles = [90, 112, 68, 90, 90, 0];
        let currentMode = "";

        const container = document.getElementById("sliders");
        joints.forEach((j, i) => {
            container.innerHTML += `<div class="slider-box"><label>${j.n}: <span id="v${i}">${j.v}</span>°</label>
            <input type="range" min="0" max="180" value="${j.v}" oninput="moveUI(${i}, this.value)"></div>`;
        });

        function log(msg) { document.getElementById("status-bar").innerText = msg; }

        function goBack(toStep) {
            fetch('/api/stop_actions');
            document.getElementById("step1").classList.add("hidden");
            document.getElementById("step2").classList.add("hidden");
            document.getElementById("step3").classList.add("hidden");
            
            if(toStep === 1) { document.getElementById("step1").classList.remove("hidden"); log("Returned to Step 1."); }
            else if(toStep === 2) { document.getElementById("step2").classList.remove("hidden"); log("Returned to Step 2."); }
        }

        function runScan() {
            let btn = document.getElementById("scan-btn");
            btn.innerText = "⏳ Scanning...";
            fetch('/api/scan').then(res=>res.json()).then(data => {
                btn.innerText = "🔍 Scan Network";
                if(data.devices.length > 0) {
                    let select = document.getElementById("device_list");
                    select.innerHTML = '<option value="">Found ' + data.devices.length + ' device(s)...</option>';
                    data.devices.forEach(dev => {
                        let displayName = dev.name !== "Unknown Device" ? `${dev.name} (${dev.ip})` : dev.ip;
                        select.innerHTML += `<option value="${dev.ip}">${displayName}</option>`;
                    });
                    select.classList.remove("hidden");
                }
            });
        }

        function updateIpField() {
            let select = document.getElementById("device_list");
            if(select.value) document.getElementById("target_ip").value = select.value;
        }

        function locateArm() {
            let ip = document.getElementById("target_ip").value;
            if(!ip || ip.trim() === "") { log("❌ Please enter or select an IP address."); return; }
            log("⏳ Verifying connection to " + ip + "...");
            fetch('/api/locate?ip=' + ip).then(res=>res.json()).then(d => {
                log(d.msg);
                if(d.success) {
                    document.getElementById("step1").classList.add("hidden");
                    document.getElementById("step2").classList.remove("hidden");
                }
            });
        }

        function showWiredSetup() { document.getElementById("wired-setup").classList.remove("hidden"); }

        function setMode(mode) {
            currentMode = mode;
            let port = document.getElementById("com_port").value;
            
            fetch(`/api/mode?m=${mode}&port=${port}`).then(res=>res.json()).then(d => {
                log(d.msg);
                if(!d.success && mode === 'wired_ui_rec') return; 
                
                document.getElementById("step2").classList.add("hidden");
                document.getElementById("step3").classList.remove("hidden");
                
                let isUI = mode.includes("ui");
                let isCobot = mode.includes("cobot");
                let isRec = mode.includes("rec");

                document.getElementById("ui-panel").classList.toggle("hidden", !isUI);
                document.getElementById("cobot-panel").classList.toggle("hidden", !isCobot);
                document.getElementById("cobot-rec-section").classList.toggle("hidden", !isRec);
                document.getElementById("playback-panel").classList.toggle("hidden", !isRec);
                
                document.getElementById("active-mode-title").innerText = "Mode: " + mode.replace(/_/g, " ").toUpperCase();
            });
        }

        function updateSettings(param, val) {
            let label = val + "ms";
            if(val <= 10) label = "Fast (" + val + "ms)";
            else if(val >= 35) label = "Slow (" + val + "ms)";
            else label = "Normal (" + val + "ms)";
            
            document.getElementById("spd_val").innerText = label;
            fetch(`/api/settings?p=${param}&v=${val}`);
        }

        function cobotPower(state) {
            fetch(`/api/cobot_power?state=${state}`).then(res=>res.json()).then(d => log(d.msg));
        }

        function moveUI(id, val) {
            document.getElementById("v"+id).innerText = val;
            currentAngles[id] = parseInt(val);
            fetch('/api/ui_move?a=' + currentAngles.join(','));
        }

        function action(cmd) {
            fetch('/api/action?cmd=' + cmd, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({angles: currentAngles})
            }).then(res=>res.json()).then(d => {
                log(d.msg);
                if(d.count !== undefined) document.getElementById("mem_count").innerText = d.count + " Frames";
            });
        }
    </script>
</body>
</html>
"""

# ==========================================
# 🌐 FLASK API ENDPOINTS
# ==========================================
@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/api/scan')
def api_scan():
    return jsonify({"devices": scan_network()})

@app.route('/api/locate')
def locate():
    global target_ip
    ip = request.args.get('ip')
    
    if ip.endswith(".local"):
        try:
            target_ip = socket.gethostbyname(ip)
            return jsonify({"success": True, "msg": f"✅ Resolved to {target_ip}"})
        except:
            return jsonify({"success": False, "msg": f"❌ Could not resolve {ip}"})
            
    try:
        response = ping(ip, timeout=0.5)
        if response is None or response is False:
            return jsonify({"success": False, "msg": f"❌ No device found at {ip}."})
    except: pass

    target_ip = ip
    return jsonify({"success": True, "msg": f"✅ Locked onto {target_ip}"})

@app.route('/api/mode')
def mode():
    global esp_serial, sys_state
    m = request.args.get('m')
    port = request.args.get('port')
    
    if "cobot" in m and not cobot_available:
        return jsonify({"success": False, "msg": "❌ myCobot not found on PI."})
        
    sys_state["mode"] = m
    
    if m == "wired_ui_rec":
        sys_state["connection"] = "wired"
        if target_ip:
            try:
                udp_socket.sendto(b"SYS:WIRED", (target_ip, target_port))
                time.sleep(1) 
            except: pass
        try:
            esp_serial = serial.Serial(port, 115200, timeout=0.1)
            return jsonify({"success": True, "msg": f"🔌 USB Mode Active ({port})"})
        except Exception as e:
            return jsonify({"success": False, "msg": f"❌ USB Error: {str(e)}"})
    else:
        sys_state["connection"] = "wifi"
        if esp_serial and esp_serial.is_open: esp_serial.close()
        return jsonify({"success": True, "msg": f"📡 Wireless Mode Active"})

@app.route('/api/settings')
def settings():
    p = request.args.get('p')
    v = float(request.args.get('v'))
    sys_state[p] = v
    return "OK"

@app.route('/api/cobot_power')
def cobot_power():
    if not cobot_available: return jsonify({"msg": "❌ Cobot not connected"})
    state = request.args.get('state')
    if state == 'lock':
        mc.power_on()
        return jsonify({"msg": "🔒 Motors Locked"})
    else:
        mc.release_all_servos()
        return jsonify({"msg": "🔓 Motors Unlocked (Free move)"})

@app.route('/api/ui_move')
def ui_move():
    if "ui" in sys_state["mode"]: send_to_esp(request.args.get('a'))
    return "OK"

@app.route('/api/stop_actions')
def stop_actions():
    sys_state["is_playing"] = False
    return "OK"

@app.route('/api/action', methods=['GET', 'POST'])
def handle_action():
    global saved_moves, sys_state, current_cobot_payload
    cmd = request.args.get('cmd')
    
    if cmd == 'record_ui':
        saved_moves.append(list(request.json['angles']))
        return jsonify({"msg": "📍 Waypoint Saved", "count": len(saved_moves)})
        
    elif cmd == 'record_cobot':
        if current_cobot_payload:
            saved_moves.append(current_cobot_payload.split(','))
            return jsonify({"msg": "📍 Checkpoint Saved", "count": len(saved_moves)})
        return jsonify({"msg": "⚠️ No data from Cobot yet"})
        
    elif cmd == 'clear':
        saved_moves.clear()
        return jsonify({"msg": "🗑️ Cleared", "count": 0})
        
    elif cmd == 'play':
        if not saved_moves: return jsonify({"msg": "⚠️ Memory Empty!"})
        sys_state["is_playing"] = True
        
        # Since we use Checkpoints now, give the robot 2.5 seconds to glide to each point
        playback_pause = 2.5 
        
        for step in saved_moves:
            if not sys_state["is_playing"]: break 
            
            # Reconstruct the payload and append the CURRENT speed limit setting
            payload = ",".join(map(str, step[:6])) + f",{int(sys_state['speed_delay'])}"
            
            if sys_state["connection"] == "wifi":
                udp_socket.sendto(payload.encode('utf-8'), (target_ip, target_port))
            elif sys_state["connection"] == "wired" and esp_serial:
                esp_serial.write(f"{payload}\n".encode('utf-8'))
                
            time.sleep(playback_pause)
            
        sys_state["is_playing"] = False
        return jsonify({"msg": "✅ Playback Complete"})
        
    return jsonify({"msg": "Unknown"})

if __name__ == '__main__':
    print("🚀 Master Hub Started! Open http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)