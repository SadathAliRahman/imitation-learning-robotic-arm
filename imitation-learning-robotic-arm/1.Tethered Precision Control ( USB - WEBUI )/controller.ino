#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// I2C pins for ESP32 (Default is 21 and 22, but we define them to be safe)
#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// --- CALIBRATION ---
#define SERVOMIN  150
#define SERVOMAX  600

// --- SPEED CONTROL ---
// Increase this number to make it SLOWER.
int MOVEMENT_DELAY = 25; // ESP32 is faster, so we can tune this lower for smoothness

// --- POSITIONS ---
// Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper
double currentAngle[6] = {90, 112, 68, 90, 90, 0}; 
int targetAngle[6]     = {90, 112, 68, 90, 90, 0}; 

unsigned long lastMoveTime = 0;

void setup() {
  // ESP32 supports high-speed Serial
  Serial.begin(115200);
  
  // Explicitly start I2C for ESP32
  Wire.begin(I2C_SDA, I2C_SCL);
  
  pwm.begin();
  pwm.setPWMFreq(50);
  
  delay(1000); // Wait for power to stabilize

  // STEP 1: GENTLE LOCK
  // Start servos at their current position to avoid jerking
  for(int i=0; i<6; i++) {
      int pulse = map(currentAngle[i], 0, 180, SERVOMIN, SERVOMAX);
      pwm.setPWM(i, 0, pulse);
      delay(150); 
  }
  
  Serial.println("ESP32 Robotic Arm Ready.");
  Serial.println("Format: [Channel]:[Angle] (e.g., 0:180)");
}

void loop() {
  // --- READ COMMANDS FROM COMPUTER ---
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim(); // Remove any whitespace/newline
    
    int colon = input.indexOf(':');
    if (colon > 0) {
      int channel = input.substring(0, colon).toInt();
      int value = input.substring(colon + 1).toInt();
      
      if (channel >= 0 && channel <= 5) {
        // Safety Limits
        if (channel == 5) value = constrain(value, 0, 80); // Gripper limit
        else value = constrain(value, 0, 180);
        
        targetAngle[channel] = value;
        Serial.print("Moving channel ");
        Serial.print(channel);
        Serial.print(" to ");
        Serial.println(value);
      }
    }
  }

  // --- THE SMOOTH MOVEMENT ENGINE ---
  if (millis() - lastMoveTime > MOVEMENT_DELAY) {
    lastMoveTime = millis();
    
    for (int i = 0; i < 6; i++) {
      if (currentAngle[i] != targetAngle[i]) {
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