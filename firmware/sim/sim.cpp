/* The orbital jig's controller, simulated: the XIAO's own program
   (firmware/orbital_jig/orbital_jig.ino, compiled as it is) driving
   simulated parts -- the DRV8833, the gearmotor and its encoder through
   the 4.7 ohm resistor, the Geneva and the ring, the home magnet and its
   Hall switch, and the phone at the end of the Bluetooth link.

   The program's time is the simulation's: it advances only inside
   delay() and delayMicroseconds(), in steps of DT, and the parts move
   while it does. Everything the program reads -- the encoder's pins, the
   switch, nFAULT -- comes from the parts at that instant, and every
   interrupt is delivered on the step its edge happens in.

   Numbers come in on the command line (--key=value) from
   tools/jig_sim.py, which takes them from the generator and the parts'
   datasheets and says which is which. Out on stdout: the program's own
   lines as it prints them, and the simulation's, each starting with '~':
   a sample of every part every SAMPLE_US, and an event for each mark,
   pin edge and shutter press. In on stdin: lines for the program, and
   lines starting with '#' for the simulation (#speed, #drag, #jam ...). */
#include <atomic>
#include <cstdarg>
#include <chrono>
#include <cstdio>
#include <deque>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "Arduino.h"
#include "BLEDevice.h"

// the program itself, as the XIAO runs it; the definitions it calls into
// (pins, clock, Serial, the BLE stack) follow it here
#include "../orbital_jig/orbital_jig.ino"

// --- parameters ---------------------------------------------------------
static std::map<std::string, double> P = {
    // supply and bridge
    {"vbus", 5.0},          // USB VBUS, through the XIAO's 5V pad to VIN
    {"r_hs", 0.200},        // DRV8833 HS FET at 5 V, 25 C (TI SLVSAR1E 6.5)
    {"r_ls", 0.160},        // DRV8833 LS FET
    {"i_ocp", 3.3},         // overcurrent trip, typical
    {"t_ocp_deg", 4e-6},    // its deglitch
    {"t_ocp", 1.35e-3},     // and how long the bridge stays off
    {"r_series", 4.7},      // the resistor in series with the motor
    // gearmotor, Pololu #5173 at 6 V
    {"ratio", 297.92}, {"v_rated", 6.0}, {"rpm_free", 100.0}, {"i_free", 0.10},
    {"i_stall", 1.6}, {"stall_kgcm", 4.0}, {"limit_kgcm", 2.0},
    {"j_rotor", 5e-9},      // kg m2 at the motor -- not published, estimated
    {"cpr", 12.0},
    // Geneva and ring
    {"geneva_n", 36}, {"geneva_c", 73.0}, {"geneva_a", 6.3624},
    {"ring_drag_nm", 0.486},   // Coulomb drag on the ring
    {"ring_j", 0.015},         // kg m2, ring + arc + carriage + phone -- estimated
    // home magnet and switch
    {"home_r", 100.0}, {"hall_z", 3.76}, {"mag_d", 3.0}, {"mag_l", 2.0}, {"mag_br", 1.44},
    {"hall_bop", 85.0}, {"hall_brp", 40.0},   // gauss, SS451A typical
    // the phone
    {"phone_connect_s", 1.5},  // a bonded phone reconnecting
    // the simulation
    // the bench: the motor alone, nothing on its shaft, the switch on its lead
    {"bench", 0},
    {"dt_us", 5}, {"sample_us", 2000}, {"speed", 1.0}, {"start_psi", 180.0},
};
static double par(const char *k) { return P[k]; }

// --- clock and output ---------------------------------------------------
static uint64_t now_us = 0;
static std::mutex out_mu;
static void emit(const std::string &line) {
  std::lock_guard<std::mutex> g(out_mu);
  fputs(line.c_str(), stdout);
  fputc('\n', stdout);
  fflush(stdout);
}
static std::string fmt(const char *f, ...) __attribute__((format(printf, 1, 2)));
static std::string fmt(const char *f, ...) {
  char b[1024];
  va_list ap;
  va_start(ap, f);
  vsnprintf(b, sizeof b, f, ap);
  va_end(ap);
  return b;
}
static double tms() { return now_us / 1000.0; }

// --- the parts' state ----------------------------------------------------
static const double KGCM = 0.0980665;     // N m per kg cm
static int pin_level[64];
static int pin_mode_[64];
static void (*isr[64])() = {nullptr};
static bool irq_on = true;

struct Motor {
  double psi = M_PI;        // output shaft, rad (driver angle = psi + slip)
  double w = 0;             // rad/s
  double i = 0;             // A, through the winding and the resistor
  double kt = 0, eta = 0, Rm = 0, i0 = 0, J = 0;
} M;
static double slip = 0;                   // the driver on its shaft, rad
static bool jam_armed = false, jammed = false;
static double jam_psi = 0;
static bool swap_motor = false, swap_enc = false, no_magnet = false, force_fault = false;
static bool ocp = false;
static double ocp_until = 0, ocp_since = -1;
static bool hall_on = false;
static bool phone_up = false, phone_allowed = true;
static BLEServer *server_ = nullptr;
static int shots = 0;
static double shutter_down_at = -1;
static double peak_tq = 0;            // through the gearbox, kg cm
static double tq_gear = 0;
static double gear_peak = 0;          // the most through the gearbox since the last sample
static double field_g = 0;            // at the switch, gauss
static double wave_t0 = -1;           // a hand waving the magnet past the switch

// Geneva: ring angle (rad) for driver angle psi, and its derivative.
// psi = pi is the lock's centre at home, as in the generator.
static void geneva(double psi, double &th, double &g, double &gp) {
  if (par("bench") != 0) { th = g = gp = 0; return; }
  double N = par("geneva_n"), C = par("geneva_c"), A = par("geneva_a");
  double step = 2 * M_PI / N, half = M_PI / 2 + M_PI / N;
  double x = psi - M_PI;
  double k = std::floor(x / (2 * M_PI));
  double f = x - k * 2 * M_PI + M_PI;     // in [pi, 3pi)
  if (f < 2 * M_PI - half) { th = k * step; g = gp = 0; return; }
  if (f > 2 * M_PI + half) { th = (k + 1) * step; g = gp = 0; return; }
  double s = std::sin(f), c = std::cos(f);
  double den = C + A * c;
  th = k * step + step / 2 + std::atan2(A * s, den);
  // d/df atan(A s / (C + A c)) = A (A + C c) / (C^2 + A^2 + 2 A C c)
  double q = C * C + A * A + 2 * A * C * c;
  g = A * (A + C * c) / q;
  gp = (-A * C * s * q + A * (A + C * c) * 2 * A * C * s) / (q * q);
}

// Bz of the magnet at the switch's element, as a function of how far the
// magnet's axis is from it sideways (mm), in gauss: a uniformly magnetized
// cylinder as two charged faces, integrated numerically once.
static std::vector<double> btab;
static const double BTAB_STEP = 0.02, BTAB_MAX = 30.0;
static void build_btab() {
  double R = par("mag_d") / 2, L = par("mag_l"), z0 = par("hall_z"), Br = par("mag_br");
  int nr = 60, nt = 96;
  for (double d = 0; d <= BTAB_MAX; d += BTAB_STEP) {
    double bz = 0;
    for (int face = 0; face < 2; face++) {
      double zf = face == 0 ? 0.0 : L;          // the near face, then the far
      double sign = face == 0 ? 1.0 : -1.0;
      double dz = z0 + zf;
      for (int a = 0; a < nr; a++) {
        double r0 = (a + 0.5) * R / nr, dr = R / nr;
        for (int b = 0; b < nt; b++) {
          double t = (b + 0.5) * 2 * M_PI / nt;
          double dx = d - r0 * std::cos(t), dy = -r0 * std::sin(t);
          double rr = std::sqrt(dx * dx + dy * dy + dz * dz);
          bz += sign * dz / (rr * rr * rr) * r0 * dr * (2 * M_PI / nt);
        }
      }
    }
    btab.push_back(std::fabs(Br / (4 * M_PI) * bz) * 1e4);   // tesla to gauss
  }
}
static double field_at(double d) {
  double x = d / BTAB_STEP;
  size_t k = (size_t)x;
  if (k + 1 >= btab.size()) return 0;
  return btab[k] + (btab[k + 1] - btab[k]) * (x - k);
}

// two channels in quadrature, cpr / 4 cycles a motor turn each
static int encA(double theta_m) {
  double e = std::fmod(theta_m / (2 * M_PI) * par("cpr") / 4.0, 1.0);
  if (e < 0) e += 1;
  return e < 0.5;
}
static int encB(double theta_m) {
  double e = std::fmod(theta_m / (2 * M_PI) * par("cpr") / 4.0 - 0.25, 1.0);
  if (e < 0) e += 1;
  return e < 0.5;
}

// --- events the page draws -------------------------------------------------
static void ev_pin(const char *name, int v) {
  emit(fmt("~{\"t\":%.3f,\"pin\":\"%s\",\"v\":%d}", tms(), name, v));
}
void sim_mark(const char *text) {
  static std::string last;
  if (last == text) return;
  last = text;
  emit(fmt("~{\"t\":%.3f,\"mark\":\"%s\"}", tms(), text));
}

// --- stdin ------------------------------------------------------------------
static std::mutex in_mu;
static std::deque<char> to_program;
static std::deque<std::string> to_sim;
static std::atomic<bool> eof{false};
static void reader() {
  char buf[512];
  while (fgets(buf, sizeof buf, stdin)) {
    std::lock_guard<std::mutex> g(in_mu);
    if (buf[0] == '#') to_sim.push_back(buf + 1);
    else for (char *c = buf; *c; c++) to_program.push_back(*c);
  }
  eof = true;
}

static void repace();
static void control(std::string l) {
  while (!l.empty() && (l.back() == '\n' || l.back() == '\r')) l.pop_back();
  size_t sp = l.find(' ');
  std::string k = l.substr(0, sp);
  double v = sp == std::string::npos ? 1 : atof(l.c_str() + sp + 1);
  if (k == "speed") { P["speed"] = v; P["sample_us"] = 2000 * std::max(1.0, v); repace(); }
  else if (k == "drag") P["ring_drag_nm"] = v;
  else if (k == "jam") { jam_armed = v != 0; if (!v) jammed = false; }
  else if (k == "slip") slip -= v * M_PI / 180;          // the driver falls behind its shaft
  else if (k == "resistor") P["r_series"] = v;
  else if (k == "swap_motor") swap_motor = v != 0;
  else if (k == "swap_encoder") swap_enc = v != 0;
  else if (k == "magnet") no_magnet = v == 0;
  else if (k == "bench") P["bench"] = v;
  else if (k == "wave") wave_t0 = now_us * 1e-6;
  else if (k == "fault") force_fault = v != 0;
  else if (k == "phone") {
    phone_allowed = v != 0;
    if (!phone_allowed && phone_up) {
      phone_up = false;
      if (server_ && server_->cb) server_->cb->onDisconnect(server_);
    }
  }
  emit(fmt("~{\"t\":%.3f,\"control\":\"%s\",\"v\":%g}", tms(), k.c_str(), v));
}

// --- one step of the parts ---------------------------------------------------
static auto wall0 = std::chrono::steady_clock::now();
static double sim_at_wall0 = 0;
static void repace() {      // count the pace again from now
  wall0 = std::chrono::steady_clock::now();
  sim_at_wall0 = now_us * 1e-6;
}
static uint64_t next_sample = 0;
static std::string edges_since;
static int last_ain1 = 0, last_ain2 = 0, last_fault = 1, last_home = 1;

static void sample() {
  double th, g, gp;
  geneva(M.psi + slip, th, g, gp);
  double tq = M.eta * M.kt * M.i / KGCM;
  emit(fmt("~{\"t\":%.3f,\"s\":{\"psi\":%.3f,\"th\":%.4f,\"rpm\":%.2f,\"i\":%.4f,\"tq\":%.4f,\"gear\":%.4f,\"b\":%.1f,"
           "\"g\":%.5f,\"p\":[%d,%d,%d,%d,%d,%d],\"enc\":%d,\"homed\":%d,\"stop\":%ld,\"lead\":%d,"
           "\"jam\":%d,\"phone\":%d,\"e\":[%s]}}",
           tms(), std::fmod((M.psi + slip) * 180 / M_PI, 360.0), th * 180 / M_PI,
           M.w * 60 / (2 * M_PI), M.i, tq, gear_peak, field_g, g, pin_level[D0], pin_level[D1], pin_level[D3],
           pin_level[D4], pin_level[D5], pin_level[D8], (int)enc, homed ? 1 : 0, stopIndex,
           (int)lead, jammed ? 1 : 0, phone_up ? 1 : 0,
           edges_since.empty() ? "" : edges_since.c_str() + 1));
  edges_since.clear();
  gear_peak = 0;
}

static void step_parts(double dt) {
  // the bridge: what AIN1/AIN2 ask for, unless overcurrent has it off
  double t = now_us * 1e-6;
  if (ocp && t >= ocp_until) ocp = false;
  int a1 = pin_level[D0], a2 = pin_level[D1];
  if (swap_motor) std::swap(a1, a2);
  double V = par("vbus"), Rs = par("r_series");
  double ke = M.kt;          // V s/rad at the output, = kt in SI
  double emf = ke * M.w;
  double i = 0;
  if (!ocp && !(a1 == 0 && a2 == 0)) {
    if (a1 && !a2) i = (V - emf) / (M.Rm + Rs + par("r_hs") + par("r_ls"));
    else if (!a1 && a2) i = (-V - emf) / (M.Rm + Rs + par("r_hs") + par("r_ls"));
    else i = -emf / (M.Rm + Rs + 2 * par("r_ls"));   // brake: both low sides on
  }
  // coast: the winding's current dies in microseconds through the body
  // diodes, and with no inductance published it is taken as gone
  if (std::fabs(i) > par("i_ocp")) {
    if (ocp_since < 0) ocp_since = t;
    if (t - ocp_since >= par("t_ocp_deg")) { ocp = true; ocp_until = t + par("t_ocp"); i = 0; }
  } else ocp_since = -1;
  M.i = i;

  // the shaft: motor torque through the gearbox, its friction, and the
  // ring through the Geneva -- reflected, with its inertia
  double th, g, gp;
  geneva(M.psi + slip, th, g, gp);
  double tq_m = M.eta * M.kt * i;
  double tq_f = M.eta * M.kt * M.i0;          // what the free-run current holds up
  double tq_ring = par("ring_drag_nm") * g;   // Coulomb on the ring, at the driver
  double J = M.J + par("ring_j") * g * g;
  double fric = tq_f + tq_ring;
  double drive = tq_m - par("ring_j") * g * gp * M.w * M.w;
  double w = M.w;
  double w_before = w;
  if (std::fabs(w) < 1e-6 && std::fabs(drive) <= fric) w = 0;
  else {
    double dir = std::fabs(w) > 1e-6 ? (w > 0 ? 1 : -1) : (drive > 0 ? 1 : -1);
    double a = (drive - dir * fric) / J;
    double w1 = w + a * dt;
    if (w != 0 && (w1 > 0) != (w > 0)) w1 = 0;   // friction stops it, it does not reverse it
    w = w1;
  }
  // a jam: something stops the ring the moment the pin starts to drive it
  if (jam_armed && !jammed && g > 0 && w > 0) { jammed = true; jam_psi = M.psi; emit(fmt("~{\"t\":%.3f,\"jam\":1}", tms())); }
  if (jammed) {
    if (M.psi + w * dt > jam_psi) { w = std::min(w, 0.0); }
    if (M.psi < jam_psi - 0.3) jammed = jam_armed = false;    // backed away from it
  }
  M.w = w;
  // what the gears carry to the driver: the ring's drag and inertia as it
  // is driven -- or, held at a jam, everything the motor makes past its
  // own friction. The rotor's inertia is before the gears and is not in it.
  double alpha = (w - w_before) / dt;
  if (jammed && w <= 0) tq_gear = std::max(0.0, std::fabs(tq_m) - tq_f);
  else tq_gear = std::fabs(par("ring_j") * (g * g * alpha + g * gp * w * w) + (w != 0 ? tq_ring : 0));
  tq_gear /= KGCM;
  double theta_m0 = M.psi * par("ratio");
  M.psi += w * dt;
  double theta_m1 = M.psi * par("ratio");
  peak_tq = std::max(peak_tq, tq_gear);
  gear_peak = std::max(gear_peak, tq_gear);

  // the encoder: every edge between the two angles, on its own step
  int A1 = encA(theta_m1), B1 = encB(theta_m1);
  if (swap_enc) std::swap(A1, B1);
  int A0 = pin_level[D3], B0 = pin_level[D4];
  (void)theta_m0;
  if (A1 != A0 || B1 != B0) {
    pin_level[D3] = A1;
    pin_level[D4] = B1;
    // every edge, while there is a speed slow enough to look at them
    if (par("speed") > 0 && par("speed") <= 2) edges_since += fmt(",[%.3f,%d,%d]", tms(), A1, B1);
    if (irq_on) {
      if (A1 != A0 && isr[D3]) isr[D3]();
      else if (B1 != B0 && isr[D4]) isr[D4]();
    }
  }

  // the home switch: the field at its element, with the datasheet's
  // operate and release points
  double ang = th;                     // the magnet rides the ring
  double d = 2 * par("home_r") * std::fabs(std::sin(ang / 2));
  if (par("bench") != 0) d = 1e9;      // on the bench the ring is not there
  if (wave_t0 >= 0) {                  // across the switch at 50 mm/s, 10 mm either side
    double x = (t - wave_t0) * 50.0 - 10.0;
    if (x > 10) wave_t0 = -1; else d = std::fabs(x);
  }
  double B = no_magnet ? 0 : field_at(d);
  field_g = B;
  if (!hall_on && B >= par("hall_bop")) hall_on = true;
  else if (hall_on && B <= par("hall_brp")) hall_on = false;
  pin_level[D5] = hall_on ? LOW : HIGH;
  pin_level[D8] = (ocp || force_fault) ? LOW : HIGH;

  // the phone: a bonded phone comes back on its own
  if (!phone_up && phone_allowed && t >= par("phone_connect_s")) {
    phone_up = true;
    if (server_ && server_->cb) server_->cb->onConnect(server_);
  }

  if (pin_level[D0] != last_ain1) ev_pin("AIN1", last_ain1 = pin_level[D0]);
  if (pin_level[D1] != last_ain2) ev_pin("AIN2", last_ain2 = pin_level[D1]);
  if (pin_level[D8] != last_fault) ev_pin("nFAULT", last_fault = pin_level[D8]);
  if (pin_level[D5] != last_home) ev_pin("HOME", last_home = pin_level[D5]);
}

static void advance(uint64_t us) {
  uint64_t end = now_us + us;
  double dt_us = par("dt_us");
  while (now_us < end) {
    uint64_t dt = std::min<uint64_t>((uint64_t)dt_us, end - now_us);
    step_parts(dt * 1e-6);
    now_us += dt;
    if (now_us >= next_sample) { sample(); next_sample = now_us + (uint64_t)par("sample_us"); }
    // controls, between steps
    {
      std::lock_guard<std::mutex> g(in_mu);
      while (!to_sim.empty()) { std::string l = to_sim.front(); to_sim.pop_front(); control(l); }
    }
    // pace against the wall clock: speed 0 runs flat out
    double sp = par("speed");
    if (sp > 0 && now_us % 1000 == 0) {
      double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
      double ahead = (now_us * 1e-6 - sim_at_wall0) / sp - wall;
      if (ahead > 0.002) std::this_thread::sleep_for(std::chrono::duration<double>(ahead));
      if (ahead < -0.25) repace();     // fell behind: start counting again
    }
  }
}

// --- the Arduino core, against the parts -------------------------------------
SimSerial Serial;
int SimSerial::available() { std::lock_guard<std::mutex> g(in_mu); return (int)to_program.size(); }
int SimSerial::read() {
  std::lock_guard<std::mutex> g(in_mu);
  if (to_program.empty()) return -1;
  char c = to_program.front();
  to_program.pop_front();
  return (unsigned char)c;
}
void SimSerial::println(const String &s) { emit(s.s); }
void pinMode(int pin, int mode) { pin_mode_[pin] = mode; }
void digitalWrite(int pin, int v) { pin_level[pin] = v ? 1 : 0; }
int digitalRead(int pin) { return pin_level[pin]; }
void attachInterrupt(int pin, void (*fn)(), int) { isr[pin] = fn; }
void noInterrupts() { irq_on = false; }
void interrupts() { irq_on = true; }
uint32_t millis() { return (uint32_t)(now_us / 1000); }
uint32_t micros() { return (uint32_t)now_us; }
void delay(uint32_t ms) { advance((uint64_t)ms * 1000); }
void delayMicroseconds(uint32_t us) { advance(us); }

void BLECharacteristic::notify() {
  if (!phone_up) return;
  if (value[0] == 0xE9 && shutter_down_at < 0) {
    shutter_down_at = tms();
    double th, g, gp;
    geneva(M.psi + slip, th, g, gp);
    shots++;
    emit(fmt("~{\"t\":%.3f,\"shot\":%d,\"th\":%.4f,\"ring_moving\":%d,\"rpm\":%.2f}", tms(), shots,
             th * 180 / M_PI, std::fabs(g * M.w) > 1e-4 ? 1 : 0, M.w * 60 / (2 * M_PI)));
  } else if (value[0] == 0 && shutter_down_at >= 0) {
    emit(fmt("~{\"t\":%.3f,\"shutter_up\":1,\"held_ms\":%.1f}", tms(), tms() - shutter_down_at));
    shutter_down_at = -1;
  }
}
void BLEServer::setCallbacks(BLEServerCallbacks *c) { cb = c; }
BLEServer *BLEDevice::createServer() { return server_ = new BLEServer(); }
void BLEDevice::startAdvertising() {}
void BLEAdvertising::start() {}

int main(int argc, char **argv) {
  for (int a = 1; a < argc; a++) {
    std::string s = argv[a];
    if (s.rfind("--", 0) != 0) continue;
    size_t eq = s.find('=');
    if (eq == std::string::npos) continue;
    P[s.substr(2, eq - 2)] = atof(s.c_str() + eq + 1);
  }
  // the motor, from the maker's four numbers at its rated voltage: the
  // winding's resistance from stall, the back-EMF constant from free
  // run, and the gearbox's efficiency from what is left of stall torque
  M.Rm = par("v_rated") / par("i_stall");
  double w_free = par("rpm_free") * 2 * M_PI / 60;
  M.kt = (par("v_rated") - par("i_free") * M.Rm) / w_free;
  M.i0 = par("i_free");
  M.eta = par("stall_kgcm") * KGCM / (M.kt * (par("i_stall") - par("i_free")));
  M.J = par("j_rotor") * par("ratio") * par("ratio");
  M.psi = par("start_psi") * M_PI / 180;
  P["sample_us"] = 2000 * std::max(1.0, par("speed"));
  build_btab();
  // where the switch operates and releases, for the page
  double d_op = 0, d_rel = 0;
  for (double d = 0; d < BTAB_MAX; d += 0.01) {
    if (field_at(d) >= par("hall_bop")) d_op = d;
    if (field_at(d) > par("hall_brp")) d_rel = d;
  }
  emit(fmt("~{\"t\":0,\"model\":{\"Rm\":%.4f,\"kt\":%.5f,\"eta\":%.4f,\"J\":%.6g,\"i0\":%.3f,"
           "\"B0\":%.1f,\"d_operate_mm\":%.3f,\"d_release_mm\":%.3f}}",
           M.Rm, M.kt, M.eta, M.J, M.i0, field_at(0), d_op, d_rel));
  for (int p = 0; p < 64; p++) pin_level[p] = 0;
  pin_level[D8] = 1;
  {
    double th, g, gp;
    geneva(M.psi, th, g, gp);
    double d = par("bench") != 0 ? 1e9 : 2 * par("home_r") * std::fabs(std::sin(th / 2));
    hall_on = !no_magnet && field_at(d) >= par("hall_bop");
    pin_level[D5] = last_home = hall_on ? LOW : HIGH;
  }
  pin_level[D3] = encA(M.psi * par("ratio"));
  pin_level[D4] = encB(M.psi * par("ratio"));
  std::thread(reader).detach();
  setup();
  sim_mark("idle: waiting for a command");
  while (!(eof && Serial.available() == 0)) loop();
  emit(fmt("~{\"t\":%.3f,\"end\":1,\"peak_kgcm\":%.4f,\"shots\":%d}", tms(), peak_tq, shots));
  return 0;
}
