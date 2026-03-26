#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ==========================================
// ⚙️ WIFI CONFIGURATION
// ==========================================
const char* ssid     = "YOUR_SSID";      // Replace with your WiFi name
const char* password = "YOUR_PASSWORD";  // Replace with your WiFi password

unsigned int localPort = 5005;

#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
WiFiUDP Udp;
char packetBuffer[255];

#define SERVOMIN  150
#define SERVOMAX  600

// Movement smoothing: Lower = Faster, Higher = Slower
int MOVEMENT_DELAY = 15; 

double currentAngle[6] = {90, 112, 68, 90, 90, 0}; 
int targetAngle[6]     = {90, 112, 68, 90, 90, 0}; 

unsigned long lastMoveTime = 0;

void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);
  
  pwm.begin();
  pwm.setPWMFreq(50);
  delay(500);

  // Initial position lock
  for(int i = 0; i < 6; i++) {
      int pulse = map(currentAngle[i], 0, 180, SERVOMIN, SERVOMAX);
      pwm.setPWM(i, 0, pulse);
  }
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n📡 WiFi Connected");
  Serial.print("📡 IP ADDRESS: ");
  Serial.println(WiFi.localIP()); 
  
  Udp.begin(localPort);
}

void loop() {
  // 1. READ INCOMING MYCOBOT ANGLES
  int packetSize = Udp.parsePacket();
  if (packetSize) {
    int len = Udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0; 
    
    char *token = strtok(packetBuffer, ",");
    int i = 0;
    while (token != NULL && i < 6) {
      int val = atoi(token);
      if (i == 5) val = constrain(val, 0, 80);  // Gripper limit
      else val = constrain(val, 0, 180);        // Arm limit
      
      targetAngle[i] = val; 
      token = strtok(NULL, ",");
      i++;
    }
  }

  // 2. SMOOTHLY CHASE THE TARGET ANGLES
  if (millis() - lastMoveTime > MOVEMENT_DELAY) {
    lastMoveTime = millis();
    for (int i = 0; i < 6; i++) {
      if ((int)currentAngle[i] != targetAngle[i]) {
        if (currentAngle[i] < targetAngle[i]) currentAngle[i] += 1;
        else currentAngle[i] -= 1;
        
        int pulse = map((int)currentAngle[i], 0, 180, SERVOMIN, SERVOMAX);
        pwm.setPWM(i, 0, pulse);
      }
    }
  }
}