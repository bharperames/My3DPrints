/* The phone end of the Bluetooth shutter, simulated. What the program
   builds -- a HID device with a consumer-control report -- is accepted as
   built; what reaches the simulated phone is the report's value on
   notify(): bit 5 of the first byte down is the shutter (Volume Increment
   in the sixteen-key media report), as the Camera app takes it. The
   phone connects when the simulation says it does (sim.cpp). */
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

#define ESP_LE_AUTH_BOND 1
#define ESP_IO_CAP_NONE 3
#define HID_KEYBOARD 0x03C1

class BLEServer;
class BLEServerCallbacks {
 public:
  virtual ~BLEServerCallbacks() {}
  virtual void onConnect(BLEServer *) {}
  virtual void onDisconnect(BLEServer *) {}
};

class BLEUUID {};
class BLEService {
 public:
  BLEUUID getUUID() { return BLEUUID(); }
};

class BLECharacteristic {
 public:
  int id = 0;
  uint8_t value[8] = {0};
  void setValue(const char *) {}
  void setValue(const std::string &) {}
  void setValue(uint8_t *v, size_t n) { for (size_t i = 0; i < n && i < 8; i++) value[i] = v[i]; }
  void notify();
};

class BLEAdvertising {
 public:
  void setAppearance(int) {}
  void addServiceUUID(BLEUUID) {}
  void start();
};

class BLEServer {
 public:
  BLEServerCallbacks *cb = nullptr;
  BLEAdvertising adv;
  void setCallbacks(BLEServerCallbacks *c);
  BLEAdvertising *getAdvertising() { return &adv; }
};

class BLEDevice {
 public:
  static void init(const char *) {}
  static BLEServer *createServer();
  static void startAdvertising();
};

class BLEHIDDevice {
 public:
  BLECharacteristic reports[4], misc;
  BLEService svc;
  explicit BLEHIDDevice(BLEServer *) {}
  BLECharacteristic *inputReport(int id) { reports[id & 3].id = id; return &reports[id & 3]; }
  BLECharacteristic *manufacturer() { return &misc; }
  void pnp(int, int, int, int) {}
  void hidInfo(int, int) {}
  void reportMap(uint8_t *, size_t) {}
  void startServices() {}
  BLEService *hidService() { return &svc; }
};

class BLESecurity {
 public:
  void setAuthenticationMode(int) {}
  void setCapability(int) {}
};
