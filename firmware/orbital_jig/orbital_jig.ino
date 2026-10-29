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

#define FW_VERSION "1.4.1"

// The fingerprint of this file as it was when loaded: "Load the program"
// writes it to fw_src.h just before compiling, and the page compares it
// with the file as it is now, so a board running an older program says so
// instead of answering "unknown command". 0 when built any other way.
#if __has_include("fw_src.h")
#include "fw_src.h"
#endif
#ifndef FW_SRC
#define FW_SRC 0
#endif

// The simulator (firmware/sim) compiles this same file on the Mac and
// defines SIM_MARK to show which part of the program is running. On the
// XIAO it is nothing.
#ifndef SIM_MARK
#define SIM_MARK(text)
#endif

// the two edges of the home switch seen during one motion
// The switch's edges in one motion: the first time it came on and the last
// time it went off, so a flicker in between moves neither; how many times
// it changed at all; and what it reads now.
struct Edges { bool sawOn = false, sawOff = false, now = false; int32_t on = 0, off = 0; int flips = 0; };

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
int32_t encOffset = 0;                   //   ... and the count kept where it truly is
bool encChecked = false;

bool homed = false;
double lockCenter = 0;                   // the count of the current stop's lock centre
long stopIndex = 0;                      // stops forward of home
int32_t homeOn = 0;                      // the switch's last on-edge, for the check
bool haveHomeOn = false;
int homeOnDir = 0;                        //   ... and the way the ring was going
int32_t lead = 60;                       // counts the brake runs on, learned

// --- Bluetooth shutter -------------------------------------------------
// A keyboard's media keys, as the selfie remotes the iPhone already trusts
// present themselves; the shutter is Volume Increment (0xE9) on the
// consumer page. Only the media keys: on NimBLE the core's
// BLEService::addCharacteristic keeps one characteristic per UUID and
// drops a second silently, and every HID input report is 0x2A4D -- so
// with a keyboard report first (1.3.1), the media-key report never
// reached the phone, which subscribed to the keyboard and never to it.
static const uint8_t REPORT_MAP[] = {
  // Sixteen on/off keys, ESP32-BLE-Keyboard's media report bit for bit: the
  // shutter is bit 5. 1.4.0 sent the key as one 16-bit usage number (an
  // array input): the phone subscribed and took every press, and neither
  // the Camera app nor the volume moved.
  0x05, 0x0C, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x01,       // consumer control, report 1
  0x05, 0x0C, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x10,
  0x09, 0xB5, 0x09, 0xB6, 0x09, 0xB7, 0x09, 0xCD,       //   next, previous, stop, play/pause
  0x09, 0xE2, 0x09, 0xE9, 0x09, 0xEA,                   //   mute, volume up (bit 5), down
  0x0A, 0x23, 0x02, 0x0A, 0x94, 0x01, 0x0A, 0x92, 0x01, //   home, my computer, calculator
  0x0A, 0x2A, 0x02, 0x0A, 0x21, 0x02, 0x0A, 0x26, 0x02, //   favorites, search, stop
  0x0A, 0x24, 0x02, 0x0A, 0x83, 0x01, 0x0A, 0x8A, 0x01, //   back, media select, mail
  0x81, 0x02,                                           //   input: data, variable, absolute
  0xC0,
};
BLEHIDDevice *hid = nullptr;
BLECharacteristic *consumer = nullptr;
volatile bool phone = false;

// What the phone has done, beyond connecting: an iPhone acts on a press
// only once the link is encrypted and it has subscribed to the report --
// and a press sent before either is dropped without a word. Each is
// reported as it happens, and with every shot, so the log shows whether
// the phone was listening.
#if defined(CONFIG_NIMBLE_ENABLED)
volatile uint16_t phoneConn = BLE_HS_CONN_HANDLE_NONE;
#endif
volatile uint16_t phoneSub = 0;          // what it wrote to the report's CCCD: 1 notify, 2 indicate
volatile int phoneEnc = -1;              // -1 not yet, 0 failed, 1 encrypted
volatile bool phoneBonded = false;

class Link : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override {
    phone = true;
    phoneSub = 0; phoneEnc = -1; phoneBonded = false;
    Serial.println("{\"ev\":\"phone\",\"connected\":true}");
  }
  void onDisconnect(BLEServer *s) override {
    phone = false;
    phoneSub = 0; phoneEnc = -1;
    Serial.println("{\"ev\":\"phone\",\"connected\":false}");
    BLEDevice::startAdvertising();
  }
#if defined(CONFIG_NIMBLE_ENABLED)
  void onConnect(BLEServer *s, ble_gap_conn_desc *d) override { phoneConn = d->conn_handle; }
#endif
};

#if defined(CONFIG_NIMBLE_ENABLED)
// Every report the phone subscribes to, and its reading of the report map:
// an iPhone that has taken the jig for a keyboard reads the map, then
// subscribes to the reports in it. Which of those it does says how far it got.
class Listening : public BLECharacteristicCallbacks {
  int report;
 public:
  Listening(int r) : report(r) {}
  void onSubscribe(BLECharacteristic *c, ble_gap_conn_desc *d, uint16_t v) override {
    if (report == 1) phoneSub = v;
    Serial.println(String("{\"ev\":\"ble\",\"what\":\"subscribed\",\"report\":\"") +
                   (report == 1 ? "shutter" : "other") + "\",\"value\":" + v + "}");
  }
  void onRead(BLECharacteristic *c, ble_gap_conn_desc *d) override {
    Serial.println("{\"ev\":\"ble\",\"what\":\"read the report map\"}");
  }
};

class Secured : public BLESecurityCallbacks {
  void onAuthenticationComplete(ble_gap_conn_desc *d, int status) override {
    phoneEnc = status == 0 && d->sec_state.encrypted ? 1 : 0;
    phoneBonded = d->sec_state.bonded;
    Serial.println(String("{\"ev\":\"ble\",\"what\":\"security\",\"status\":") + status +
                   ",\"encrypted\":" + (d->sec_state.encrypted ? "true" : "false") +
                   ",\"bonded\":" + (d->sec_state.bonded ? "true" : "false") + "}");
  }
};
#endif

void bleStart() {
  BLEDevice::init("Orbital Jig");
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new Link());
  hid = new BLEHIDDevice(server);
  consumer = hid->inputReport(1);         // the one input report: see REPORT_MAP
#if defined(CONFIG_NIMBLE_ENABLED)
  consumer->setCallbacks(new Listening(1));
  BLEDevice::setSecurityCallbacks(new Secured());
#endif
  hid->manufacturer()->setValue("My3DPrints");
  hid->pnp(0x02, 0xe502, 0xa111, 0x0210);
  hid->hidInfo(0x00, 0x01);
  hid->reportMap((uint8_t *)REPORT_MAP, sizeof(REPORT_MAP));
#if defined(CONFIG_NIMBLE_ENABLED)
  if (BLECharacteristic *map = hid->hidService()->getCharacteristic(BLEUUID((uint16_t)0x2a4b)))
    map->setCallbacks(new Listening(0));
#endif
  hid->startServices();
  BLESecurity *sec = new BLESecurity();
  sec->setAuthenticationMode(ESP_LE_AUTH_BOND);
  sec->setCapability(ESP_IO_CAP_NONE);
  BLEAdvertising *adv = server->getAdvertising();
  adv->setAppearance(HID_KEYBOARD);
  adv->addServiceUUID(hid->hidService()->getUUID());
  adv->start();
}

// The report, to every phone that has asked for it. On the S3 the core
// (3.3.12) runs NimBLE, and its BLECharacteristic::notify() asserts that
// the characteristic's service knows its server -- which it did not: the
// first press on Brett's phone rebooted the XIAO. NimBLE's own call sends
// the value just set, read back through the characteristic.
// Returns NimBLE's answer, 0 when the stack took it for sending.
int sendReport(uint8_t *v) {
  consumer->setValue(v, 2);
#if defined(CONFIG_NIMBLE_ENABLED)
  if (phoneConn == BLE_HS_CONN_HANDLE_NONE) return -1;
  return ble_gatts_notify_custom(phoneConn, consumer->getHandle(), ble_hs_mbuf_from_flat(v, 2));
#else
  consumer->notify();
  return 0;
#endif
}

String shotSays = "";     // what the last press found: for the reply
bool shutter() {
  if (!phone) return false;
  uint8_t down[2] = {0x20, 0x00}, up[2] = {0x00, 0x00};   // bit 5: Volume Increment
  int rcDown = sendReport(down);
  delay(60);                // a press, not a hold: held, the Camera app records video
  int rcUp = sendReport(up);
  shotSays = String(",\"sent\":[") + rcDown + "," + rcUp + "],\"subscribed\":" + phoneSub +
             ",\"encrypted\":" + phoneEnc + ",\"bonded\":" + (phoneBonded ? "true" : "false");
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
  return c * encSign + encOffset;
}

bool hall() { return digitalRead(PIN_HOME) == LOW; }

// A change of the switch is believed once it has read the same this many
// times running. Brett's first runs logged it flickering on and off with
// the ring standing still; a few hundred microseconds of agreement costs
// a homing edge a few counts, the same on the way in as on the way out.
const int HALL_SAME = 5;
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
  int32_t cCheck = count(), c0 = cCheck;
  bool h = hall();
  int hallRun = 0;
  if (edges) edges->now = h;
  drive(dir);
  while (!done(count())) {
    uint32_t now = millis();
    if (fault()) { drive(0); return "the DRV8833 reported a fault"; }
    if (stopAsked()) { drive(0); return "stopped"; }
    if (hall() != h) {
      if (++hallRun >= HALL_SAME) {
        h = !h;
        hallRun = 0;
        if (edges) {
          edges->now = h;
          edges->flips++;
          if (h) { if (!edges->sawOn) { edges->sawOn = true; edges->on = count(); } }
          else { edges->sawOff = true; edges->off = count(); }
        }
      }
    } else hallRun = 0;
    if (!encChecked && now - t0 > START_GRACE_MS) {
      // the first motion tells us which way the encoder counts
      int32_t moved = count() - cCheck;
      if (abs(moved) > 4 * STALL_COUNTS) {
        if ((moved > 0) != (dir > 0)) {
          // the motor went `dir` all along: count it so, from where this
          // motion began, and carry on. (Until 1.1.0 this stopped and the
          // caller tried again with a target worked out the wrong way
          // round; Home, which does not try again, failed outright.)
          encSign = -encSign;
          encOffset = 0;
          encOffset = cCheck - moved - count();
          if (edges) *edges = Edges();        // edges seen so far were counted backward
          Serial.println("{\"ev\":\"note\",\"what\":\"the encoder counts the other way; corrected\"}");
        }
        encChecked = true;
      }
    }
    if (now - tCheck >= STALL_MS && now - t0 > START_GRACE_MS) {
      if (abs(count() - cCheck) < STALL_COUNTS) {
        drive(0);
        // what the encoder saw, so a stalled motor and a silent encoder can
        // be told apart from the log: a motor that ran with no counts is
        // the encoder's wiring; a few counts and then none is a bind
        return "jam: the encoder stopped counting (" + String(count() - c0) + " counts in " +
               String(now - t0) + " ms; A " + digitalRead(PIN_ENC_A) + ", B " + digitalRead(PIN_ENC_B) + ")";
      }
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
  int32_t t = lround(target);
  int dir = t >= count() ? 1 : -1;
  String err = move(dir, [&](int32_t c) { return dir > 0 ? c >= t - lead : c <= t + lead; },
                    edges, limitMs);
  if (err.length()) return err;
  SIM_MARK("brake: let it come to rest, learn the overrun");
  delay(120);
  int32_t over = (count() - t) * dir;          // past the target, positive
  lead = constrain(lead + over / 2, 0, 400);
  return "";
}

void reply(const String &json) { Serial.println(json); }
void error(const String &what) { reply("{\"ev\":\"error\",\"what\":\"" + what + "\"}"); }

// --- the commands ------------------------------------------------------
void cmdHello() {
  reply(String("{\"ev\":\"hello\",\"fw\":\"") + FW_VERSION + "\",\"src\":" + String((uint32_t)FW_SRC) +
        ",\"turn\":" + String(TURN, 2) +
        ",\"stops\":" + STOPS + ",\"homed\":" + (homed ? "true" : "false") +
        ",\"stop\":" + stopIndex + ",\"phone\":" + (phone ? "true" : "false") +
        ",\"subscribed\":" + phoneSub + ",\"encrypted\":" + phoneEnc +
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

// Drive for `ms` milliseconds, back if negative, with no jam check: to
// free a ring that a jam has stopped, and to see whether the encoder
// counts at all. The 4.7 ohm caps a stall at ~0.6 A, inside what the
// gearbox takes, and a jog is a second at most. The ring's place is
// lost, so Home comes after.
void cmdJog(int ms) {
  SIM_MARK("jog: drive for a moment, no jam check");
  homed = false;
  int dir = ms < 0 ? -1 : 1;
  uint32_t t0 = millis(), len = abs(ms);
  int32_t c0 = count();
  String why = "";
  drive(dir);
  while (millis() - t0 < len) {
    if (fault()) { why = "the DRV8833 reported a fault"; break; }
    if (stopAsked()) { why = "stopped"; break; }
    delayMicroseconds(200);
  }
  drive(0);
  delay(120);
  if (why.length()) { error(why); return; }
  // a free jog learns the encoder's direction as a first move would, so
  // the counts below read positive forward
  int32_t moved = count() - c0;
  if (!encChecked && abs(moved) > 4 * STALL_COUNTS) {
    if ((moved > 0) != (dir > 0)) { encSign = -encSign; encOffset = 0; encOffset = c0 - moved - count(); }
    encChecked = true;
  }
  reply("{\"ev\":\"jogged\",\"ms\":" + String(ms) + ",\"counts\":" + String(count() - c0) +
        ",\"hall\":" + (hall() ? "true" : "false") + ",\"A\":" + digitalRead(PIN_ENC_A) +
        ",\"B\":" + digitalRead(PIN_ENC_B) + "}");
}

const int32_t HOME_CLEAR = 400;          // counts of off before the magnet has gone
const int32_t HOME_SPAN_MIN = 1500;      // the switch on for less than this is a dropout
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
  //
  // The magnet has gone only once the switch has stayed off for HOME_CLEAR
  // counts: with the phone connected Brett's switch has dropped out for
  // tens of milliseconds with the magnet over it, and a Home that took the
  // first drop for the far edge parked a third of a turn early (spans of
  // 490 and 518 counts, where 2,700 is the switch's own).
  SIM_MARK("home: forward until the magnet comes and goes");
  int32_t c0 = count();
  String err = move(1, [&](int32_t c) { return e.sawOn && e.sawOff && !e.now && c - e.off > HOME_CLEAR; },
                    &e, (STOPS + 2) * TURN_LIMIT_MS);
  if (err.length()) { error(err); return; }
  if (e.off - e.on > 1.6 * TURN) { error("the home switch stayed on too long"); return; }
  if (e.off - e.on < HOME_SPAN_MIN) {
    error("the home switch was on for only " + String(e.off - e.on) +
          " counts, where it should be about 2,700: it is dropping out over the magnet");
    return;
  }
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
        ",\"hall\":" + (hall() ? "true" : "false") + ",\"flicker\":" + String(e.flips > 2 ? e.flips - 2 : 0) +
        ",\"ms\":" + String(millis() - t0) + "}");
}

// k stops forward, or back when k is negative: the Geneva runs either
// way, a driver turn backward taking the ring back one stop.
void cmdStep(int k) {
  SIM_MARK("step: one driver turn per stop");
  if (!homed) { error("not homed"); return; }
  if (k == 0) { error("step needs a number of stops, + or -"); return; }
  int dir = k > 0 ? 1 : -1;
  String ms = "";
  double check = NAN;       // the home switch's own view of where the lock is
  for (int i = 0; i < abs(k); i++) {
    Edges e;
    uint32_t t0 = millis();
    String err = moveTo(lockCenter + dir * TURN, &e, TURN_LIMIT_MS);
    if (err.length()) { error(err + " (stop " + String(stopIndex + dir) + ")"); return; }
    lockCenter += dir * TURN;
    stopIndex += dir;
    ms += (ms.length() ? "," : "") + String(millis() - t0);
    // leaving home, the edge from the move in and this one's straddle the
    // lock it left: how far that is from where the counts put it, in
    // degrees of the driver's turn
    // Only forward crossings pair up. The switch's hysteresis puts each
    // edge on the near side of the magnet, so a pair's middle sits off the
    // lock by the same small amount every time it is crossed forward --
    // the way Home crosses it, so that lands on the lock Home set -- and
    // the other way backward: crossed backward, the check would read the
    // hysteresis twice over, not the drive.
    if (e.sawOn) { homeOn = e.on; haveHomeOn = true; homeOnDir = dir; }
    if (dir > 0 && e.sawOff && haveHomeOn && homeOnDir == dir) {
      double mid = (homeOn + e.off) / 2.0;
      check = (mid - (lockCenter - dir * TURN)) * 360.0 / TURN;
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
  // the tray's 10 k pulls it up; the XIAO's own (~45 k) as well, so a
  // joint gone open on the 10 k reads as "no magnet", not as noise
  pinMode(PIN_HOME, INPUT_PULLUP);
  pinMode(PIN_FAULT, INPUT_PULLUP);
  encState = (digitalRead(PIN_ENC_A) << 1) | digitalRead(PIN_ENC_B);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), encEdge, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), encEdge, CHANGE);
  bleStart();
}

bool lastHall = false;
int idleRun = 0;
void loop() {
  // the switch, reported as it changes while nothing is moving: the bench
  // test waves the magnet past it. A change is reported once it has held
  // for 20 ms (ten turns of this loop).
  if (hall() != lastHall) {
    if (++idleRun >= 10) {
      lastHall = !lastHall;
      idleRun = 0;
      reply(String("{\"ev\":\"hall\",\"on\":") + (lastHall ? "true" : "false") + "}");
    }
  } else idleRun = 0;
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
    else if (cmd == "jog") cmdJog(constrain(arg, -1000, 1000));
    else if (cmd == "step") cmdStep(constrain(arg, -STOPS, STOPS));
    else if (cmd == "shoot") {
      SIM_MARK("shoot: volume-up to the phone");
      if (shutter()) reply("{\"ev\":\"shot\"" + shotSays + "}");
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
