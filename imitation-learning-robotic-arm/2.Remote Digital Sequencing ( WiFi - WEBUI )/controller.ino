#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ==========================================
// ⚙️ WIFI CONFIGURATION
// ==========================================
const char* ssid     = "sadath";
const char* password = "YOUR_PASSWORD"; // Replace with your actual password

unsigned int localPort = 5005;

// I2C pins for ESP32
#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
WiFiUDP Udp;
char packetBuffer[255];

// --- CALIBRATION ---
#define SERVOMIN  150
#define SERVOMAX  600

// --- SPEED CONTROL ---
// Lower = Faster, Higher = Slower
int MOVEMENT_DELAY = 15; 

// Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper
double currentAngle[6] = {90, 112, 68, 90, 90, 0}; 
int targetAngle[6]     = {90, 112, 68, 90, 90, 0}; 

unsigned long lastMoveTime = 0;

void setup() {
  Serial.begin(115200);
  
  // Start I2C
  Wire.begin(I2C_SDA, I2C_SCL);
  pwm.begin();
  pwm.setPWMFreq(50);
  delay(500);

  // 1. GENTLE LOCK TO SAFE START
  Serial.println("🔒 Locking to Safe Start...");
  for(int i = 0; i < 6; i++) {
      int pulse = map(currentAngle[i], 0, 180, SERVOMIN, SERVOMAX);
      pwm.setPWM(i, 0, pulse);
  }
  
  // 2. CONNECT TO WIFI
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n✅ WiFi Connected!");
  Serial.print("📡 IP ADDRESS: ");
  Serial.println(WiFi.localIP()); 
  
  // 3. START LISTENING
  Udp.begin(localPort);
  Serial.println("🎧 Listening for Web Commands...");
}

void loop() {
  // --- 1. READ COMMANDS OVER WIFI ---
  int packetSize = Udp.parsePacket();
  if (packetSize) {
    int len = Udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0; // Null-terminate the string
    
    // Parse the incoming string: e.g., "90,112,68,90,90,0"
    char *token = strtok(packetBuffer, ",");
    int i = 0;
    while (token != NULL && i < 6) {
      int val = atoi(token);
      
      // Safety Limits
      if (i == 5) {
          val = constrain(val, 0, 80); // Gripper limit
      } else {
          val = constrain(val, 0, 180); // Arm limits
      }
      
      targetAngle[i] = val; // Update the destination
      token = strtok(NULL, ",");
      i++;
    }
  }

  // --- 2. THE SMOOTH MOVEMENT ENGINE ---
  if (millis() - lastMoveTime > MOVEMENT_DELAY) {
    lastMoveTime = millis();
    
    for (int i = 0; i < 6; i++) {
      if ((int)currentAngle[i] != targetAngle[i]) {
        // Move 1 degree closer
        if (currentAngle[i] < targetAngle[i]) currentAngle[i] += 1;
        else currentAngle[i] -= 1;
        
        // Update Servo
        int pulse = map((int)currentAngle[i], 0, 180, SERVOMIN, SERVOMAX);
        pwm.setPWM(i, 0, pulse);
      }
    }
  }
}