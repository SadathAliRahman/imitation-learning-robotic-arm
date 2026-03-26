from flask import Flask, render_template_string, jsonify
import socket
import time
import threading
from pymycobot.mycobot import MyCobot

app = Flask(__name__)

# ==========================================
# ⚙️ CONFIGURATION & HARDWARE
# ==========================================
ESP32_IP = "0.0.0.0"  # Replace with your actual ESP32 IP
ESP32_PORT = 5005
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

try:
    mc = MyCobot('/dev/ttyAMA0', 1000000)
    mc.release_all_servos() # Start unlocked
except Exception as e:
    print(f"Hardware Error: {e}")

# Global Memory
recorded_waypoints = []
is_playing = False # Prevents live streaming while playing a sequence

# ==========================================
# 🔄 CORE FUNCTIONS
# ==========================================
def map_angle(val, in_min, in_max, out_min, out_max):
    mapped = (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return max(min(int(mapped), out_max), out_min)

def get_current_payload():
    """Reads cobot and formats string for ESP32."""
    angles = mc.get_angles()
    if angles and len(angles) >= 5:
        base     = map_angle(angles[0], -90, 90, 0, 180)
        shoulder = map_angle(angles[1], -90, 90, 0, 180)
        elbow    = map_angle(angles[2], -90, 90, 0, 180)
        w_pitch  = map_angle(angles[3], -90, 90, 0, 180)
        w_roll   = map_angle(angles[4], -90, 90, 0, 180)
        return f"{base},{shoulder},{elbow},{w_pitch},{w_roll},0"
    return None

def live_stream_thread():
    """Runs constantly in the background to mirror movements."""
    global is_playing
    while True:
        if not is_playing:
            payload = get_current_payload()
            if payload:
                udp_socket.sendto(payload.encode('utf-8'), (ESP32_IP, ESP32_PORT))
        time.sleep(0.05) # 20Hz update rate

# Start the background mirroring immediately
threading.Thread(target=live_stream_thread, daemon=True).start()

# ==========================================
# 🌐 WEB ROUTES (API ENDPOINTS)
# ==========================================
@app.route('/unlock', methods=['POST'])
def unlock():
    mc.release_all_servos()
    return jsonify({"status": "Unlocked! You can move the arm."})

@app.route('/lock', methods=['POST'])
def lock():
    mc.power_on()
    return jsonify({"status": "Locked! Arm is holding position."})

@app.route('/record', methods=['POST'])
def record():
    payload = get_current_payload()
    if payload:
        recorded_waypoints.append(payload)
        return jsonify({"status": f"Recorded Waypoint {len(recorded_waypoints)}!"})
    return jsonify({"status": "Failed to read angles."}), 400

@app.route('/play', methods=['POST'])
def play():
    global is_playing, recorded_waypoints
    if not recorded_waypoints:
        return jsonify({"status": "Nothing to play! Record first."})
    
    is_playing = True # Pause the live mirror
    
    # Send waypoints with a 1-second delay between each
    for payload in recorded_waypoints:
        udp_socket.sendto(payload.encode('utf-8'), (ESP32_IP, ESP32_PORT))
        time.sleep(1.0) 
        
    is_playing = False # Resume live mirror
    return jsonify({"status": "Playback complete! Back to live mode."})

@app.route('/clear', methods=['POST'])
def clear():
    global recorded_waypoints
    recorded_waypoints = []
    return jsonify({"status": "Memory cleared."})

# ==========================================
# 🎨 THE USER INTERFACE (HTML/JS)
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Cobot Teach & Play</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; text-align: center; background: #121212; color: white; padding: 20px; }
        .btn { display: block; width: 90%; max-width: 400px; margin: 15px auto; padding: 20px; font-size: 20px; font-weight: bold; border: none; border-radius: 10px; cursor: pointer; color: white; transition: 0.2s;}
        .btn:active { transform: scale(0.95); }
        .btn-unlock { background: #4CAF50; }
        .btn-lock { background: #F44336; }
        .btn-record { background: #2196F3; }
        .btn-play { background: #9C27B0; }
        .btn-clear { background: #607D8B; }
        #statusBox { margin-top: 20px; padding: 15px; background: #1e1e1e; border-radius: 8px; font-family: monospace; color: #00FF00;}
    </style>
</head>
<body>
    <h2>🤖 Teach & Play Controller</h2>
    
    <button class="btn btn-unlock" onclick="sendCommand('/unlock')">🔓 UNLOCK (Free Move)</button>
    <button class="btn btn-lock" onclick="sendCommand('/lock')">🔒 LOCK (Hold Position)</button>
    
    <hr style="border-color: #333; margin: 30px 0;">
    
    <button class="btn btn-record" onclick="sendCommand('/record')">📍 RECORD WAYPOINT</button>
    <button class="btn btn-play" onclick="sendCommand('/play')">▶️ PLAY SEQUENCE</button>
    <button class="btn btn-clear" onclick="sendCommand('/clear')">🗑️ CLEAR MEMORY</button>

    <div id="statusBox">System Ready. Waiting for commands...</div>

    <script>
        function sendCommand(endpoint) {
            document.getElementById('statusBox').innerText = "Processing...";
            fetch(endpoint, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('statusBox').innerText = data.status;
                })
                .catch(err => {
                    document.getElementById('statusBox').innerText = "Network Error!";
                });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)