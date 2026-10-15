/* The orbital jig's controller: a Seeed XIAO ESP32S3 in the box beside
   the jig, run from the Mac over its USB-C cable.

   It does four things and nothing else. It turns the Geneva's driver --
   one turn is one 10 degree stop of the ring -- through a DRV8833, and
   counts the turn on the gearmotor's encoder. It watches the Hall switch
   under the ring for the home magnet. And it is a Bluetooth shutter
   remote: paired with the phone, it presses volume-up, which the Camera
   app takes as the shutter.

   The sequence of a capture -- which stops to visit, how long to let the
   arc settle, when to wait for the carriage to be moved by hand -- is
   the Mac's (tools/jig_run.py). This only answers commands, one line
   each, and every answer is one line of JSON:

     hello            what this is, and its state
     spin N           N driver turns with nothing on the shaft: the bench test
     home             find the magnet and stop in the lock at home
     step K           K stops forward, each ending in the middle of the lock
     shoot            press the phone's shutter
     hall             the home switch, now
     stop             brake, whatever is running

   Every motion ends braked, and stops on its own if the encoder stops
   counting (a jam) or the DRV8833 reports a fault. The 4.7 ohm resistor
   in series with the motor is what keeps a jam from hurting the gearbox;
   this only keeps it from lasting.

   The wiring and the counts are the generator's (tools/gen_orbital_jig.py:
   WIRES, MOTOR["counts"]); tests/test_jig_firmware.py holds them to it. */

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLESecurity.h>
#include <HIDTypes.h>

#define FW_VERSION "1.0.0"

// The simulator (firmware/sim) compiles this same file on the Mac and
// defines SIM_MARK to show which part of the program is running. On the
// XIAO it is nothing.
#ifndef SIM_MARK
#define SIM_MARK(text)
#endif

// the two edges of the home switch seen during one motion
struct Edges { bool sawOn = false, sawOff = false; int32_t on = 0, off = 0; };

// --- the wiring (WIRES in the generator) -------------------------------
const int PIN_AIN1 = D0;     // DRV8833: AIN1 high, AIN2 low drives forward
const int PIN_AIN2 = D1;
const int PIN_ENC_A = D3;    // encoder A, yellow
const int PIN_ENC_B = D4;    // encoder B, white
const int PIN_HOME = D5;     // SS451A, open collector, 10 k to 3V3: low on the magnet
const int PIN_FAULT = D8;    // DRV8833 nFAULT, open drain: low on a fault

// --- the drive ---------------------------------------------------------
// 12 counts a motor turn on both edges of both channels, through a
// 297.92:1 gearbox: counts per turn of the driver, which is one stop.
const double TURN = 12.0 * 297.92;
const int STOPS = 36;                    // GENEVA_N
const uint32_t STALL_MS = 250;           // no progress this long while driving is a jam
const int32_t STALL_COUNTS = 25;         //   ... where progress is this many counts
const uint32_t START_GRACE_MS = 300;     // the motor's own spin-up
const uint32_t TURN_LIMIT_MS = 3000;     // a turn takes ~0.7 s at 5 V

volatile int32_t enc = 0;                // the raw quadrature count
volatile uint8_t encState = 0;
int encSign = 1;                         // flipped if the motor's wires run the other way
bool encChecked = false;

bool homed = false;
double lockCenter = 0;                   // the count of the current stop's lock centre
long stopIndex = 0;                      // stops forward of home
int32_t homeOn = 0;                      // the switch's last on-edge, for the check
bool haveHomeOn = false;
int32_t lead = 60;                       // counts the brake runs on, learned

// --- Bluetooth shutter -------------------------------------------------
// A keyboard and a consumer-control report, as the selfie remotes the
// iPhone already trusts present themselves; the shutter is Volume
// Increment (0xE9) on the consumer page.
static const uint8_t REPORT_MAP[] = {
  0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x85, 0x01,       // keyboard, report 1
  0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01,
  0x75, 0x01, 0x95, 0x08, 0x81, 0x02,                   //   modifiers
  0x95, 0x01, 0x75, 0x08, 0x81, 0x01,                   //   reserved
  0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65,
  0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00,       //   six keys
  0xC0,
  0x05, 0x0C, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x02,       // consumer control, report 2
  0x15, 0x00, 0x26, 0xFF, 0x03, 0x19, 0x00, 0x2A, 0xFF, 0x03,
  0x75, 0x10, 0x95, 0x01, 0x81, 0x00,                   //   one 16-bit usage
  0xC0,
};
BLEHIDDevice *hid = nullptr;
BLECharacteristic *consumer = nullptr;
volatile bool phone = false;

class Link : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override {
    phone = true;
    Serial.println("{\"ev\":\"phone\",\"connected\":true}");
  }
  void onDisconnect(BLEServer *s) override {
    phone = false;
    Serial.println("{\"ev\":\"phone\",\"connected\":false}");
    BLEDevice::startAdvertising();
  }
};

void bleStart() {
  BLEDevice::init("Orbital Jig");
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new Link());
  hid = new BLEHIDDevice(server);
  hid->inputReport(1);
  consumer = hid->inputReport(2);
  hid->manufacturer()->setValue("My3DPrints");
  hid->pnp(0x02, 0xe502, 0xa111, 0x0210);
  hid->hidInfo(0x00, 0x01);
  hid->reportMap((uint8_t *)REPORT_MAP, sizeof(REPORT_MAP));
  hid->startServices();
  BLESecurity *sec = new BLESecurity();
  sec->setAuthenticationMode(ESP_LE_AUTH_BOND);
  sec->setCapability(ESP_IO_CAP_NONE);
  BLEAdvertising *adv = server->getAdvertising();
  adv->setAppearance(HID_KEYBOARD);
  adv->addServiceUUID(hid->hidService()->getUUID());
  adv->start();
}

bool shutter() {
  if (!phone) return false;
  uint8_t down[2] = {0xE9, 0x00}, up[2] = {0x00, 0x00};
  consumer->setValue(down, 2);
  consumer->notify();
  delay(60);                // a press, not a hold: held, the Camera app records video
  consumer->setValue(up, 2);
  consumer->notify();
  return true;
}

// --- the encoder -------------------------------------------------------
// Gray-code transitions, previous two bits and new two bits: +1, -1, or 0
// for no change or a missed state.
static const int8_t QDEC[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};

void IRAM_ATTR encEdge() {
  uint8_t s = (digitalRead(PIN_ENC_A) << 1) | digitalRead(PIN_ENC_B);
  enc += QDEC[(encState << 2) | s];
  encState = s;
}

int32_t count() {
  noInterrupts();
  int32_t c = enc;
  interrupts();
  return c * encSign;
}

bool hall() { return digitalRead(PIN_HOME) == LOW; }
bool fault() { return digitalRead(PIN_FAULT) == LOW; }

void drive(int dir) {       // +1 forward, -1 back, 0 brake
  if (dir > 0) { digitalWrite(PIN_AIN2, LOW); digitalWrite(PIN_AIN1, HIGH); }
  else if (dir < 0) { digitalWrite(PIN_AIN1, LOW); digitalWrite(PIN_AIN2, HIGH); }
  else { digitalWrite(PIN_AIN1, HIGH); digitalWrite(PIN_AIN2, HIGH); }
}

// --- one motion --------------------------------------------------------
// Drive in `dir` until `done` says so, watching for a jam, a fault, a
// `stop` from the Mac and the home switch's edges. Returns "" or what
// went wrong.
String lineIn;
bool stopAsked() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      String l = lineIn; lineIn = "";
      l.trim();
      if (l == "stop") return true;
    } else if (lineIn.length() < 120) lineIn += ch;
  }
  return false;
}

template <typename Done>
String move(int dir, Done done, Edges *edges, uint32_t limitMs) {
  uint32_t t0 = millis(), tCheck = t0;
  int32_t cCheck = count();
  bool h = hall();
  drive(dir);
  while (!done(count())) {
    uint32_t now = millis();
    if (fault()) { drive(0); return "the DRV8833 reported a fault"; }
    if (stopAsked()) { drive(0); return "stopped"; }
    bool hn = hall();
    if (hn != h && edges) {
      if (hn) { edges->sawOn = true; edges->on = count(); }
      else { edges->sawOff = true; edges->off = count(); }
    }
    h = hn;
    if (!encChecked && now - t0 > START_GRACE_MS) {
      // the first motion tells us which way the encoder counts
      int32_t moved = count() - cCheck;
      if (abs(moved) > 4 * STALL_COUNTS) {
        if ((moved > 0) != (dir > 0)) {
          encSign = -encSign;
          Serial.println("{\"ev\":\"note\",\"what\":\"the encoder counts the other way; corrected\"}");
          drive(0);
          return "retry";
        }
        encChecked = true;
      }
    }
    if (now - tCheck >= STALL_MS && now - t0 > START_GRACE_MS) {
      if (abs(count() - cCheck) < STALL_COUNTS) { drive(0); return "jam: the encoder stopped counting"; }
      tCheck = now; cCheck = count();
    }
    if (now - t0 > limitMs) { drive(0); return "took too long"; }
    delayMicroseconds(200);
  }
  drive(0);
  return "";
}

// brake `lead` counts early, then learn the lead from where it came to rest
String moveTo(double target, Edges *edges, uint32_t limitMs) {
  for (int attempt = 0; attempt < 2; attempt++) {
    int32_t t = lround(target);
    int dir = t >= count() ? 1 : -1;
    String err = move(dir, [&](int32_t c) { return dir > 0 ? c >= t - lead : c <= t + lead; },
                      edges, limitMs);
    if (err == "retry") continue;
    if (err.length()) return err;
    SIM_MARK("brake: let it come to rest, learn the overrun");
    delay(120);
    int32_t over = (count() - t) * dir;          // past the target, positive
    lead = constrain(lead + over / 2, 0, 400);
    return "";
  }
  return "the encoder would not agree with the motor";
}

void reply(const String &json) { Serial.println(json); }
void error(const String &what) { reply("{\"ev\":\"error\",\"what\":\"" + what + "\"}"); }

// --- the commands ------------------------------------------------------
void cmdHello() {
  reply(String("{\"ev\":\"hello\",\"fw\":\"") + FW_VERSION + "\",\"turn\":" + String(TURN, 2) +
        ",\"stops\":" + STOPS + ",\"homed\":" + (homed ? "true" : "false") +
        ",\"stop\":" + stopIndex + ",\"phone\":" + (phone ? "true" : "false") +
        ",\"hall\":" + (hall() ? "true" : "false") + ",\"fault\":" + (fault() ? "true" : "false") + "}");
}

void cmdSpin(int n) {
  SIM_MARK("spin: whole turns, nothing on the shaft");
  // the bench: nothing on the shaft, so no stop to aim for
  homed = false;
  for (int i = 1; i <= n; i++) {
    int32_t c0 = count();
    uint32_t t0 = millis();
    String err = moveTo(c0 + TURN, nullptr, TURN_LIMIT_MS);
    if (err.length()) { error(err); return; }
    reply("{\"ev\":\"turn\",\"n\":" + String(i) + ",\"counts\":" + String(count() - c0) +
          ",\"ms\":" + String(millis() - t0) + ",\"lead\":" + String(lead) + "}");
  }
  reply("{\"ev\":\"done\",\"cmd\":\"spin\"}");
}

void cmdHome() {
  homed = false;
  Edges e;
  uint32_t t0 = millis();
  // on the magnet already: back off it first, so the way in is seen
  if (hall()) {
    SIM_MARK("home: on the magnet already, back off it");
    String err = move(-1, [](int32_t) { return !hall(); }, nullptr, 2 * TURN_LIMIT_MS);
    if (err.length()) { error(err); return; }
    int32_t c = count();
    err = moveTo(c - TURN / 4, nullptr, TURN_LIMIT_MS);
    if (err.length()) { error(err); return; }
  }
  // forward until the magnet comes over the switch and leaves it again:
  // the two edges are symmetric about the lock's centre, whatever
  // distance the switch happens to answer at
  SIM_MARK("home: forward until the magnet comes and goes");
  int32_t c0 = count();
  String err = move(1, [&](int32_t c) { return e.sawOn && e.sawOff && e.off > e.on; },
                    &e, (STOPS + 2) * TURN_LIMIT_MS);
  if (err.length()) { error(err); return; }
  if (e.off - e.on > 1.6 * TURN) { error("the home switch stayed on too long"); return; }
  double mid = (e.on + e.off) / 2.0;
  SIM_MARK("home: back to the lock's centre, between the two edges");
  err = moveTo(mid, nullptr, TURN_LIMIT_MS);
  if (err.length()) { error(err); return; }
  homed = true;
  haveHomeOn = false;
  lockCenter = mid;
  stopIndex = 0;
  reply("{\"ev\":\"homed\",\"turns\":" + String((e.on - c0) / TURN, 2) +
        ",\"on\":" + String(e.on) + ",\"off\":" + String(e.off) +
        ",\"hall\":" + (hall() ? "true" : "false") + ",\"ms\":" + String(millis() - t0) + "}");
}

void cmdStep(int k) {
  SIM_MARK("step: one driver turn per stop");
  if (!homed) { error("not homed"); return; }
  String ms = "";
  double check = NAN;       // the home switch's own view of where the lock is
  for (int i = 0; i < k; i++) {
    Edges e;
    uint32_t t0 = millis();
    String err = moveTo(lockCenter + TURN, &e, TURN_LIMIT_MS);
    if (err.length()) { error(err + " (stop " + String(stopIndex + 1) + ")"); return; }
    lockCenter += TURN;
    stopIndex++;
    ms += (ms.length() ? "," : "") + String(millis() - t0);
    // leaving home, the edge from the move in and this one's straddle the
    // lock it left: how far that is from where the counts put it, in
    // degrees of the driver's turn
    if (e.sawOn) { homeOn = e.on; haveHomeOn = true; }
    if (e.sawOff && haveHomeOn) {
      double mid = (homeOn + e.off) / 2.0;
      check = (mid - (lockCenter - TURN)) * 360.0 / TURN;
      haveHomeOn = false;
    }
  }
  bool h = hall();
  bool atHome = stopIndex % STOPS == 0;
  String out = "{\"ev\":\"stepped\",\"k\":" + String(k) + ",\"stop\":" + String(stopIndex) +
               ",\"ms\":[" + ms + "],\"hall\":" + (h ? "true" : "false") +
               ",\"home_expected\":" + (atHome ? "true" : "false");
  if (!isnan(check)) out += ",\"home_check_deg\":" + String(check, 1);
  out += "}";
  reply(out);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  drive(0);
  pinMode(PIN_ENC_A, INPUT);       // open drain, 10 k pull-ups on the encoder's board
  pinMode(PIN_ENC_B, INPUT);
  pinMode(PIN_HOME, INPUT);        // the tray's 10 k pulls it up
  pinMode(PIN_FAULT, INPUT_PULLUP);
  encState = (digitalRead(PIN_ENC_A) << 1) | digitalRead(PIN_ENC_B);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), encEdge, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), encEdge, CHANGE);
  bleStart();
}

bool lastHall = false;
void loop() {
  // the switch, reported as it changes while nothing is moving: the bench
  // test waves the magnet past it
  bool h = hall();
  if (h != lastHall) {
    lastHall = h;
    reply(String("{\"ev\":\"hall\",\"on\":") + (h ? "true" : "false") + "}");
  }
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch != '\n' && ch != '\r') {
      if (lineIn.length() < 120) lineIn += ch;
      continue;
    }
    String l = lineIn; lineIn = "";
    l.trim();
    if (!l.length()) continue;
    int sp = l.indexOf(' ');
    String cmd = sp < 0 ? l : l.substring(0, sp);
    int arg = sp < 0 ? 1 : l.substring(sp + 1).toInt();
    if (cmd == "hello") cmdHello();
    else if (cmd == "spin") cmdSpin(constrain(arg, 1, 50));
    else if (cmd == "home") cmdHome();
    else if (cmd == "step") cmdStep(constrain(arg, 1, STOPS));
    else if (cmd == "shoot") {
      SIM_MARK("shoot: volume-up to the phone");
      if (shutter()) reply("{\"ev\":\"shot\"}");
      else error("the phone is not connected");
    }
    else if (cmd == "hall") reply(String("{\"ev\":\"hall\",\"on\":") + (hall() ? "true" : "false") + "}");
    else if (cmd == "stop") { drive(0); reply("{\"ev\":\"stopped\"}"); }
    else error("unknown command: " + cmd);
    lastHall = hall();
    SIM_MARK("idle: waiting for a command");
  }
  delay(2);
}
