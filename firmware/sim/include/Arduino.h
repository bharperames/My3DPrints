/* Just enough of the Arduino core for the orbital jig's program to compile
   and run on the Mac, against simulated parts instead of pins. Every
   function the program calls lands in sim.cpp, which owns the clock: time
   passes only in delay() and delayMicroseconds(), the way the program
   spends it on the XIAO, and the parts move while it does. */
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>

#define IRAM_ATTR
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define CHANGE 3

// the XIAO ESP32S3's pads, as its variant names them (pins_arduino.h)
#define D0 1
#define D1 2
#define D2 3
#define D3 4
#define D4 5
#define D5 6
#define D6 43
#define D7 44
#define D8 7
#define D9 8
#define D10 9

void pinMode(int pin, int mode);
void digitalWrite(int pin, int v);
int digitalRead(int pin);
void attachInterrupt(int irq, void (*fn)(), int mode);
inline int digitalPinToInterrupt(int pin) { return pin; }
void noInterrupts();
void interrupts();
uint32_t millis();
uint32_t micros();
void delay(uint32_t ms);
void delayMicroseconds(uint32_t us);
void sim_mark(const char *text);
#define SIM_MARK(text) sim_mark(text)

template <typename T, typename L, typename H>
T constrain(T x, L lo, H hi) { return x < lo ? (T)lo : x > hi ? (T)hi : x; }
using std::lround;
using std::isnan;
using std::abs;

class String {
 public:
  std::string s;
  String() {}
  String(const char *c) : s(c ? c : "") {}
  String(const std::string &x) : s(x) {}
  String(char c) : s(1, c) {}
  String(int v) : s(std::to_string(v)) {}
  String(long v) : s(std::to_string(v)) {}
  String(unsigned v) : s(std::to_string(v)) {}
  String(unsigned long v) : s(std::to_string(v)) {}
  String(double v, int dp = 2) {
    char b[64];
    snprintf(b, sizeof b, "%.*f", dp, v);
    s = b;
  }
  unsigned length() const { return s.size(); }
  void trim() {
    size_t a = s.find_first_not_of(" \t\r\n");
    size_t b = s.find_last_not_of(" \t\r\n");
    s = a == std::string::npos ? "" : s.substr(a, b - a + 1);
  }
  int indexOf(char c) const { size_t i = s.find(c); return i == std::string::npos ? -1 : (int)i; }
  String substring(unsigned a) const { return a >= s.size() ? String() : String(s.substr(a)); }
  String substring(unsigned a, unsigned b) const { return String(s.substr(a, b - a)); }
  long toInt() const { return std::strtol(s.c_str(), nullptr, 10); }
  const char *c_str() const { return s.c_str(); }
  bool operator==(const char *o) const { return s == o; }
  bool operator==(const String &o) const { return s == o.s; }
  bool operator!=(const char *o) const { return s != o; }
  String &operator+=(const String &o) { s += o.s; return *this; }
  String &operator+=(const char *o) { s += o; return *this; }
  String &operator+=(char c) { s += c; return *this; }
};
inline String operator+(const String &a, const String &b) { return String(a.s + b.s); }
inline String operator+(const String &a, const char *b) { return String(a.s + b); }
inline String operator+(const char *a, const String &b) { return String(std::string(a) + b.s); }
inline String operator+(const String &a, int b) { return a + String(b); }
inline String operator+(const String &a, long b) { return a + String(b); }

class SimSerial {
 public:
  void begin(long) {}
  int available();
  int read();
  void println(const String &s);
  void println(const char *s) { println(String(s)); }
};
extern SimSerial Serial;
