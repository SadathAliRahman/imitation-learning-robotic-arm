import serial
import time
from flask import Flask, render_template_string, request

# ==========================================
# ⚙️ WIRED CONFIGURATION
# ==========================================
SERIAL_PORT = 'COM13'  # <-- Change this if your Arduino IDE shows a different port
BAUD_RATE = 115200

app = Flask(__name__)
saved_moves = []

# Connect to the ESP32 via USB
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    time.sleep(2) # Give the ESP32 a second to reset upon connection
    print(f"✅ Connected to Robot Arm on {SERIAL_PORT}!")
except Exception as e:
    print(f"❌ Connection Failed: Check if {SERIAL_PORT} is correct. Error: {e}")
    ser = None

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Wired Teach & Play</title>
    <style>
        body { background-color: #1e1e1e; color: white; font-family: sans-serif; text-align: center; padding: 20px; }
        .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; max-width: 600px; margin: 0 auto; }
        .slider-box { background: #333; padding: 15px; border-radius: 8px; }
        input[type=range] { width: 100%; margin-top: 10px; }
        .btn-group { margin-top: 30px; display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; }
        button { padding: 15px 25px; font-size: 1.1rem; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; color: white; transition: 0.2s;}
        button:active { transform: scale(0.95); }
        .btn-save { background-color: #ff9800; }
        .btn-play { background-color: #4caf50; }
        .btn-clear { background-color: #f44336; }
        #status { color: #00FF00; margin-top: 20px; font-family: monospace; font-size: 1.2rem; }
        #saved-list { text-align: left; max-width: 600px; margin: 20px auto; background: #111; padding: 15px; border-radius: 8px; min-height: 50px; font-family: monospace;}
    </style>
</head>
<body>
    <h2>🔌 Wired Control Panel</h2>
    
    <div class="controls" id="sliders"></div>

    <div class="btn-group">
        <button class="btn-save" onclick="savePosition()">📍 Record Position</button>
        <button class="btn-play" onclick="playSequence()">▶️ Play Sequence</button>
        <button class="btn-clear" onclick="clearSequence()">🗑️ Clear</button>
    </div>

    <div id="status">System Ready.</div>
    <div id="saved-list">Memory Empty.</div>

    <script>
        const joints = [
            { id: 0, name: "Base", val: 90 },
            { id: 1, name: "Shoulder", val: 112 },
            { id: 2, name: "Elbow", val: 68 },
            { id: 3, name: "Wrist Pitch", val: 90 },
            { id: 4, name: "Wrist Roll", val: 90 },
            { id: 5, name: "Gripper", val: 0 }
        ];

        let currentAngles = [90, 112, 68, 90, 90, 0];

        const container = document.getElementById("sliders");
        joints.forEach((j, idx) => {
            let div = document.createElement("div");
            div.className = "slider-box";
            div.innerHTML = `
                <label><b>${j.name}</b>: <span id="v${idx}">${j.val}</span>°</label>
                <input type="range" min="0" max="180" value="${j.val}" 
                       oninput="move(${idx}, this.value)">
            `;
            container.appendChild(div);
        });

        function move(id, val) {
            document.getElementById("v" + id).innerText = val;
            currentAngles[id] = parseInt(val);
            fetch(`/move?c=${id}&v=${val}`);
        }

        function savePosition() {
            fetch('/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({angles: currentAngles})
            })
            .then(res => res.json())
            .then(data => {
                document.getElementById("status").innerText = "✅ Saved Step " + data.count;
                updateList(data.moves);
            });
        }

        function playSequence() {
            document.getElementById("status").innerText = "▶️ Playing Sequence...";
            fetch('/play').then(res => res.text()).then(txt => {
                document.getElementById("status").innerText = txt;
            });
        }

        function clearSequence() {
            fetch('/clear').then(() => {
                document.getElementById("saved-list").innerHTML = "Memory Empty.";
                document.getElementById("status").innerText = "🗑️ Cleared.";
            });
        }

        function updateList(moves) {
            let html = "";
            moves.forEach((move, i) => {
                html += `<div>Step ${i+1}: [${move.join(", ")}]</div>`;
            });
            document.getElementById("saved-list").innerHTML = html;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

# --- WIRED ROUTES ---
@app.route('/move')
def move():
    c = request.args.get('c')
    v = request.args.get('v')
    if ser and ser.is_open:
        ser.write(f"{c}:{v}\\n".encode())
    return "OK"

@app.route('/save', methods=['POST'])
def save():
    data = request.json
    saved_moves.append(list(data['angles']))
    return {"count": len(saved_moves), "moves": saved_moves}

@app.route('/play')
def play():
    if not saved_moves:
        return "⚠️ Memory Empty!"
         
    if ser and ser.is_open:
        for step in saved_moves:
            for channel, angle in enumerate(step):
                ser.write(f"{channel}:{angle}\\n".encode())
                time.sleep(0.05) 
            time.sleep(2.0) 
            
    return "✅ Playback Complete"

@app.route('/clear')
def clear():
    saved_moves.clear()
    return "Cleared"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)