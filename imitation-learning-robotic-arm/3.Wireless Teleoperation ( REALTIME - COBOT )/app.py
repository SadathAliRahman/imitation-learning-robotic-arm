import socket
import time
from pymycobot.mycobot import MyCobot

# ==========================================
# ⚙️ NETWORK CONFIGURATION
# ==========================================
ESP32_IP = "0.0.0.0"  # Replace with your ESP32 IP before running
ESP32_PORT = 5005     # Must match the localPort in your ESP32 code

# Initialize myCobot 280 Pi (Serial port for Raspberry Pi version)
mc = MyCobot('/dev/ttyAMA0', 1000000)

# Setup UDP Socket for sending data
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Relax all servos so you can physically move the myCobot (Demonstration Mode)
mc.release_all_servos()
print("🤖 myCobot relaxed. Ready for demonstration!")
print(f"📡 Broadcasting real-time angles to ESP32 at {ESP32_IP}:{ESP32_PORT}...")

# ==========================================
# 🔄 REAL-TIME MAPPING & STREAMING
# ==========================================
def map_angle(val, in_min, in_max, out_min, out_max):
    """Maps myCobot joint angles to standard 0-180 degree servo angles."""
    mapped = (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return max(min(int(mapped), out_max), out_min) # Keep it safely between 0 and 180

while True:
    try:
        # 1. Read the current physical angles of the myCobot
        angles = mc.get_angles()
        
        if angles and len(angles) >= 5:
            # 2. Map myCobot's angles (often negative/positive) to the 0-180 scale
            # NOTE: You will need to tweak the -90 to 90 range based on your actual calibration
            base     = map_angle(angles[0], -90, 90, 0, 180)
            shoulder = map_angle(angles[1], -90, 90, 0, 180)
            elbow    = map_angle(angles[2], -90, 90, 0, 180)
            w_pitch  = map_angle(angles[3], -90, 90, 0, 180)
            w_roll   = map_angle(angles[4], -90, 90, 0, 180)
            gripper  = 0 # Replace with myCobot gripper data if you are using one
            
            # 3. Format the data exactly as the ESP32 expects: "Base,Shoulder,Elbow,WristPitch,WristRoll,Gripper"
            payload = f"{base},{shoulder},{elbow},{w_pitch},{w_roll},{gripper}"
            
            # 4. Fire the data over Wi-Fi
            udp_socket.sendto(payload.encode('utf-8'), (ESP32_IP, ESP32_PORT))
            print(f"Streaming: {payload}")
            
        # Run at roughly 20Hz to prevent network flooding and allow the ESP32 to keep up smoothly
        time.sleep(0.05) 
        
    except KeyboardInterrupt:
        print("\nStopping demonstration streaming...")
        break
    except Exception as e:
        print(f"Error reading from cobot: {e}")
        time.sleep(0.1)