"""The orbital jig's controller program, held to the generator's wiring and
run against its simulated parts.

The simulator compiles the program the XIAO runs, unchanged, so these
are tests of that program: it homes from anywhere, every step ends in the
lock, a revolution comes back to the magnet, a jam stops it, a slipped
set screw is caught, and the 4.7 ohm is what keeps a jam under the
gearbox's limit -- shown by taking it out.
"""
import os
import re
import shutil
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gen_orbital_jig as J  # noqa: E402
import jig_control as C  # noqa: E402

INO = os.path.join(C.FIRMWARE, "orbital_jig.ino")
FAST = 200          # the simulator's speed: two hundred times real time


def read(path):
    with open(path) as f:
        return f.read()


def lock_error(psi):
    """Degrees from the nearest lock centre (psi = 180 mod 360)."""
    return abs((psi - 180.0 + 180.0) % 360.0 - 180.0)


class Sim:
    def __init__(self, **kw):
        self.jig = C.Jig()
        self.jig.connect("sim", speed=kw.pop("speed", FAST), **kw)
        self.ask("hello", "hello")

    def ask(self, cmd, ev, timeout=120):
        return self.jig.ask(cmd, lambda d: d.get("ev") == ev, timeout)

    def settle(self):
        time.sleep(0.15)        # the samples after the brake's last word
        return self.jig.trace[-1][1]["s"]

    def peak_gear(self, after=0):
        return max(d["s"]["gear"] for s, d in self.jig.trace if s > after)

    def close(self):
        self.jig.disconnect()


class TestProgram(unittest.TestCase):
    def test_the_program_drives_the_pins_the_tray_wires(self):
        src = read(INO)
        pins = dict(re.findall(r"const int PIN_(\w+) = (D\d+);", src))
        wired = {}
        for w in J.WIRES:
            ends = (w[3], w[4])
            for e in ends:
                if e[0] == "xiao":
                    wired[w[2]] = e[1]
        self.assertEqual(pins["AIN1"], wired["AIN1"])
        self.assertEqual(pins["AIN2"], wired["AIN2"])
        self.assertEqual(pins["FAULT"], wired["nFAULT"])
        self.assertEqual(pins["ENC_A"], wired["encoder A"])
        self.assertEqual(pins["ENC_B"], wired["encoder B"])
        self.assertEqual(pins["HOME"], wired["home"])

    def test_the_program_counts_a_turn_as_the_motor_does(self):
        src = read(INO)
        m = re.search(r"const double TURN = ([\d.]+) \* ([\d.]+);", src)
        self.assertAlmostEqual(float(m.group(1)) * float(m.group(2)), J.MOTOR["counts"], places=6)
        self.assertIn(f"const int STOPS = {J.GENEVA_N};", src)

    def test_the_simulation_runs_the_generators_geneva(self):
        self.assertEqual(C.SPEC["geneva_n"], J.GENEVA_N)
        self.assertEqual(C.SPEC["geneva_c"], J.GENEVA_C)
        self.assertAlmostEqual(C.SPEC["geneva_a"], J.GENEVA_A)
        self.assertEqual(C.SPEC["r_series"], J.MOTOR_R)
        self.assertEqual(C.SPEC["home_r"], J.HOME["r"])
        # every ring of the protocol a whole number of stops, 108 frames
        self.assertEqual(sum(r["frames"] for r in C.RINGS), 108)
        for r in C.RINGS:
            self.assertEqual(r["frames"] * r["stops"], J.GENEVA_N)

    @unittest.skipUnless(shutil.which("arduino-cli") and os.path.isdir(
        os.path.expanduser("~/Library/Arduino15/packages/esp32")), "no ESP32 toolchain")
    def test_the_program_compiles_for_the_xiao(self):
        r = subprocess.run([C.ARDUINO_CLI, "compile", "-b", C.FQBN, "--build-path",
                            os.path.join(C.ROOT, "firmware", "build"), C.FIRMWARE],
                           capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])


class TestSimulated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        C.build_sim()

    def test_it_homes_from_anywhere_into_the_lock(self):
        for start in (0, 97, 180, 265, 300, 455 % 360):
            s = Sim(start_psi=start)
            try:
                d = s.ask("home", "homed")
                st = s.settle()
                self.assertTrue(d["hall"], f"from {start}: not on the magnet")
                self.assertLess(lock_error(st["psi"]), 30, f"from {start}: driver at {st['psi']}")
                self.assertAlmostEqual(st["th"] % 360, 0.0, places=2)
            finally:
                s.close()

    def test_a_revolution_steps_36_stops_and_comes_back_to_the_magnet(self):
        s = Sim(start_psi=220)
        try:
            s.ask("home", "homed")
            for k in range(1, 37):
                d = s.ask("step 1", "stepped")
                st = s.settle()
                self.assertEqual(d["hall"], d["home_expected"], f"stop {k}")
                self.assertLess(lock_error(st["psi"]), 30, f"stop {k}")
                self.assertAlmostEqual(st["th"], 10.0 * k, places=2)
            self.assertTrue(d["hall"])
        finally:
            s.close()

    def test_a_jam_stops_it_and_the_resistor_keeps_it_under_the_gearbox_limit(self):
        limit = C.SPEC["limit_kgcm"]
        peaks = {}
        for r_series in (C.SPEC["r_series"], 0.0):
            s = Sim()
            try:
                s.ask("home", "homed")
                s.jig.control(f"resistor {r_series}")
                s.jig.control("jam 1")
                time.sleep(0.05)
                mark = s.jig.seq
                with self.assertRaisesRegex(RuntimeError, "jam"):
                    s.ask("step 1", "stepped")
                time.sleep(0.15)
                peaks[r_series] = s.peak_gear(mark)
            finally:
                s.close()
        # the negative control: the same jam without the resistor breaks the limit
        self.assertLess(peaks[C.SPEC["r_series"]], limit)
        self.assertGreater(peaks[0.0], limit)

    def test_a_slipped_set_screw_is_caught_at_home(self):
        s = Sim()
        try:
            s.ask("home", "homed")
            s.jig.control("slip 60")
            checks = []
            for _ in range(37):
                d = s.ask("step 1", "stepped")
                if "home_check_deg" in d:
                    checks.append(d["home_check_deg"])
            self.assertTrue(checks, "never passed home")
            self.assertAlmostEqual(abs(checks[0]), 60.0, delta=3.0)
        finally:
            s.close()

    def test_a_capture_takes_108_photos_all_with_the_ring_still(self):
        jig = C.Jig()
        jig.connect("sim", speed=FAST, start_psi=33)
        jig.settings.update(settle_s=0.005, after_shot_s=0.005)
        try:
            jig.start_capture()
            end = time.time() + 600
            while time.time() < end:
                st = jig.run["state"]
                if st == "elevation":
                    jig.proceed()
                    time.sleep(0.05)
                if st in ("done", "failed", "stopped"):
                    break
                time.sleep(0.02)
            self.assertEqual(jig.run["state"], "done", jig.run["message"])
            time.sleep(0.2)
            self.assertEqual(len(jig.shots), 108)
            self.assertFalse([s for s in jig.shots if s["ring_moving"]])
            for s in jig.shots:
                self.assertAlmostEqual(s["th"] / 10.0, round(s["th"] / 10.0), places=3)
        finally:
            jig.disconnect()



class BoardWithNoProgram(unittest.TestCase):
    """A load cut off partway leaves the XIAO restarting ten times a second,
    each time printing its boot report: the controller says so once and keeps
    the report out of the log, and lets go when the program answers."""

    # as the XIAO printed it on 2026-10-29, after a load that failed halfway
    LOOP = ["\ufffd\x01\x11\x02\x00\ufffdESP-ROM:esp32s3-20210327", "Build:Mar 27 2021",
            "rst:0x3 (RTC_SW_SYS_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)", "Saved PC:0x403cd0e9", "SPIWP:0xee",
            "mode:DIO, clock div:1", "load:0x3fce2820,len:0x10cc", "load:0x403c8700,len:0xc2c",
            "load:0x403cb700,len:0x30b0", "entry 0x403c88b8",
            "E (106) esp_image: invalid segment length 0x2000e136",
            "E (107) boot: OTA app partition slot 0 is not bootable",
            "E (107) esp_image: image at 0x340000 has invalid magic byte (nothing flashed here?)",
            "E (112) boot: OTA app partition slot 1 is not bootable",
            "E (117) boot: No bootable app partitions in the partition table"]

    def test_a_boot_loop_is_one_note_not_a_flood(self):
        jig = C.Jig()
        for _ in range(50):
            for line in self.LOOP:
                jig._line(line)
        st = jig.state()
        self.assertEqual(st["board"], "no program")
        self.assertEqual(st["resets"], 50)
        notes = [(d["ev"], d["state"]) for d in st["log"] if d.get("ev") == "board"]
        self.assertEqual(notes, [("board", "no program")])
        self.assertLess(len(st["log"]), 2 * len(self.LOOP), "the restarts after the first still reach the log")
        jig._line('{"ev":"hello","fw":"1.3.1"}')
        self.assertIsNone(jig.state()["board"])

    def test_the_loader_is_named_and_its_lines_kept(self):
        jig = C.Jig()
        for line in ("rst:0x15 (USB_UART_CHIP_RESET),boot:0x0 (DOWNLOAD(USB/UART0))", "Saved PC:0x40034f84",
                     "waiting for download"):
            jig._line(line)
        st = jig.state()
        self.assertEqual(st["board"], "in loader")
        self.assertEqual(sum(d.get("ev") == "text" for d in st["log"]), 3)

    def test_a_hello_does_not_hold_back_new_code(self):
        jig = C.Jig()
        jig.link = type("Quiet", (), {"kind": "xiao", "write": lambda self, line: None})()
        jig.send("hello")
        self.assertTrue(jig.idle())
        jig.send("home")
        self.assertFalse(jig.idle())


if __name__ == "__main__":
    unittest.main()
