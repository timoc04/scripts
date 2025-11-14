// === Seeed Studio XIAO ESP32C3 – Sacoa Spark trigger ===
// Detecteert sluiting op D1 en stuurt het woord "TRIGGER" via USB-serieel

const int PIN_PULSE = D1;
const unsigned long DEBOUNCE_MS = 150;

unsigned long lastMs = 0;
int lastState = HIGH;

void setup() {
  pinMode(PIN_PULSE, INPUT_PULLUP);   // gebruik interne pull-up naar 3.3V
  Serial.begin(9600);                 // COM-poort: match met Python
}

void loop() {
  int s = digitalRead(PIN_PULSE);
  unsigned long now = millis();

  // Detecteer flank (hoog -> laag) met debounce
  if (lastState == HIGH && s == LOW && (now - lastMs) > DEBOUNCE_MS) {
    Serial.println("TRIGGER");       // Stuur commando 'TRIGGER' naar PC
    lastMs = now;
  }
  lastState = s;
}