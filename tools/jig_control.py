#!/usr/bin/env python3
"""The orbital jig's controller, from the Mac: the real one on its USB
cable, or the simulated one -- the same program, compiled for the Mac and
run against simulated parts (firmware/sim) -- behind the same interface.

The XIAO's program only answers commands. The capture is here: home,
then for each ring of the protocol wait for the carriage to be set by
hand, and for each frame step the ring, let it settle, press the phone's
shutter, and move on -- checking at every pass of home that the ring is
where the counts say.

The shop's server holds one Jig and the page talks to it (serve.py,
/jig/...). From a shell:

    python tools/jig_control.py sim "spin 3" "home" "step 4" "shoot"
    python tools/jig_control.py flash          # build and load the XIAO
"""
import glob
import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIRMWARE = os.path.join(ROOT, "firmware", "orbital_jig")
SIM_DIR = os.path.join(ROOT, "firmware", "sim")
SIM_BIN = os.path.join(SIM_DIR, "build", "jig_sim")
FQBN = "esp32:esp32:XIAO_ESP32S3"
ARDUINO_CLI = shutil.which("arduino-cli") or "/opt/homebrew/bin/arduino-cli"

sys.path.insert(0, HERE)
import gen_orbital_jig as J  # noqa: E402

# --- what the simulation is made of ------------------------------------
# Every number the simulated parts run on, and where it came from. The
# page shows this table: a number marked "estimate" is one nobody has
# measured or published, and the first thing to replace with a
# measurement.
ARC_LEG_R = math.hypot((J.ARC_RI + J.ARC_RO) / 2, J.Y_ARC) / 1000.0   # m

SPECS = [
    # supply and bridge
    dict(key="vbus", value=5.0, unit="V", source="USB VBUS, through the XIAO's 5V pad (USB 2.0: 4.75-5.25)"),
    dict(key="r_hs", value=0.200, unit="ohm", source="TI DRV8833 datasheet 6.5: HS FET at 5 V, 25 C, typical"),
    dict(key="r_ls", value=0.160, unit="ohm", source="TI DRV8833 datasheet 6.5: LS FET at 5 V, 25 C, typical"),
    dict(key="i_ocp", value=3.3, unit="A", source="TI DRV8833 datasheet 6.5: overcurrent trip, typical (2.0 min)"),
    dict(key="t_ocp_deg", value=4e-6, unit="s", source="TI DRV8833 datasheet 6.5: OCP deglitch"),
    dict(key="t_ocp", value=1.35e-3, unit="s", source="TI DRV8833 datasheet 6.5: OCP retry period"),
    dict(key="r_series", value=J.MOTOR_R, unit="ohm", source="generator: MOTOR_R, the resistor in series with the motor"),
    # gearmotor
    dict(key="ratio", value=297.92, unit=":1", source="Pololu #5173: 297.92:1 exactly"),
    dict(key="v_rated", value=6.0, unit="V", source="Pololu #5173: rated voltage"),
    dict(key="rpm_free", value=100.0, unit="rpm", source="Pololu #5173: no-load speed at 6 V"),
    dict(key="i_free", value=0.10, unit="A", source="Pololu #5173: no-load current at 6 V"),
    dict(key="i_stall", value=1.6, unit="A", source="Pololu #5173: stall current at 6 V"),
    dict(key="stall_kgcm", value=4.0, unit="kg cm", source="Pololu #5173: stall torque at 6 V"),
    dict(key="limit_kgcm", value=2.0, unit="kg cm", source="Pololu #5173: gearbox's instantaneous torque limit"),
    dict(key="j_rotor", value=5e-9, unit="kg m2", source="estimate: rotor of a micro metal motor (not published)"),
    dict(key="cpr", value=12.0, unit="counts", source="Pololu #5173: 12 CPR on both edges of both channels"),
    # Geneva and ring
    dict(key="geneva_n", value=J.GENEVA_N, unit="slots", source="generator: GENEVA_N"),
    dict(key="geneva_c", value=J.GENEVA_C, unit="mm", source="generator: GENEVA_C"),
    dict(key="geneva_a", value=J.GENEVA_A, unit="mm", source="generator: GENEVA_A, the crank"),
    dict(key="ring_drag_nm", value=0.300 * 9.80665 * ARC_LEG_R, unit="N m",
         source="estimate: 300 g pulled at the arc's leg -- replace with the pull test"),
    dict(key="ring_j", value=0.015, unit="kg m2", source="estimate: ring, arc, carriage and phone about the axis"),
    # home switch
    dict(key="home_r", value=J.HOME["r"], unit="mm", source="generator: HOME r, the magnet and switch"),
    dict(key="hall_z", value=J.HOME["gap"] + 0.2 + 0.46 + 0.1, unit="mm",
         source="generator: HOME gap 3.0 + the pocket's 0.2 + the SS451A's element 0.46 under its face"
                " (Honeywell drawing) + the magnet seated 0.1 up"),
    dict(key="mag_d", value=J.MAGNET[0], unit="mm", source="generator: MAGNET, a 3 x 2 disc"),
    dict(key="mag_l", value=J.MAGNET[1], unit="mm", source="generator: MAGNET"),
    dict(key="mag_br", value=1.44, unit="T", source="N52 remanence, 1.42-1.47 T"),
    dict(key="hall_bop", value=85.0, unit="G", source="Honeywell SS451A: operate point, typical (35-135)"),
    dict(key="hall_brp", value=40.0, unit="G", source="Honeywell SS451A: release point, typical (10-120)"),
    dict(key="phone_connect_s", value=1.5, unit="s", source="estimate: a bonded iPhone reconnecting"),
]
SPEC = {s["key"]: s["value"] for s in SPECS}

# The capture: the generator's protocol, in whole stops
STOP_DEG = 360.0 / J.GENEVA_N
RINGS = [dict(ring=p["ring"], name=p["name"], elev=p["elev"],
              stops=int(round(p["step"] / STOP_DEG)),
              frames=int(round(360.0 / p["step"]))) for p in J.PROTOCOL]


def drag_from_pull(grams):
    """The ring's drag torque (N m) from a pull test at the arc's leg."""
    return grams / 1000.0 * 9.80665 * ARC_LEG_R


# --- the simulator's binary ----------------------------------------------
def sim_sources():
    return [os.path.join(SIM_DIR, "sim.cpp"), os.path.join(FIRMWARE, "orbital_jig.ino")] + \
        glob.glob(os.path.join(SIM_DIR, "include", "*.h"))


_BUILD = threading.Lock()


def build_sim(force=False):
    """Compile the simulator when anything it is made from is newer than
    it. Returns the binary's path."""
    with _BUILD:
        return _build_sim(force)


def _build_sim(force):
    srcs = sim_sources()
    if not force and os.path.exists(SIM_BIN) and \
            os.path.getmtime(SIM_BIN) >= max(os.path.getmtime(s) for s in srcs):
        return SIM_BIN
    os.makedirs(os.path.dirname(SIM_BIN), exist_ok=True)
    tmp = SIM_BIN + ".new"
    cmd = ["clang++", "-std=c++17", "-O2", "-Wall", "-Wno-unused-function",
           "-I" + os.path.join(SIM_DIR, "include"), "-o", tmp,
           os.path.join(SIM_DIR, "sim.cpp")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("the simulator did not compile:\n" + r.stderr[-2000:])
    os.replace(tmp, SIM_BIN)       # never a half-written binary under its name
    return SIM_BIN


# --- the XIAO's program -----------------------------------------------------
def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[0] if ports else None


# Which server process this is: the page starts its log over when it
# changes, as it does when the server restarts itself on new code.
BOOT = time.time()

# What the ESP32-S3 prints when it cannot run the program. With nothing it
# can start (a load cut off partway leaves a half-written image) it resets
# and says so again about every tenth of a second, which floods the log; in
# its loader it waits for a program and runs nothing until reset.
NO_PROGRAM = re.compile(r"No bootable app partitions|app partition slot \d+ is not bootable")
IN_LOADER = re.compile(r"waiting for download")
# the boot report's lines, held back while the board has no program: one
# explanation in the log instead of fifteen lines ten times a second
BOOT_REPORT = re.compile(r"ESP-ROM:|^Build:|^rst:0x|^Saved PC:|^SPIWP:|^mode:(DIO|QIO|DOUT|QOUT)|"
                         r"^load:0x|^entry 0x|^E \(\d+\) (esp_image|boot):")


def source_print():
    """The program file's fingerprint, as a number: the board reports the
    one it was compiled from in its hello, so the page can tell a board
    running an older program than the file from one that is up to date."""
    with open(os.path.join(FIRMWARE, "orbital_jig.ino"), "rb") as f:
        return int(hashlib.sha256(f.read()).hexdigest()[:8], 16)


def _run_streaming(args, on_line, timeout=600):
    """Run arduino-cli, handing each line of its output to `on_line` as it
    comes -- esptool redraws its progress with carriage returns, so those
    end a line too. Returns (exit code, the output's tail)."""
    p = subprocess.Popen([ARDUINO_CLI] + args, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    killer = threading.Timer(timeout, p.kill)
    killer.start()
    out, buf = [], b""
    try:
        while True:
            chunk = p.stdout.read1(4096)
            if not chunk:
                break
            buf += chunk
            *lines, buf = re.split(rb"[\r\n]", buf)
            for ln in lines:
                text = ln.decode(errors="replace").strip()
                if text:
                    out.append(text)
                    # progress is news, not the job: a fault in reporting it
                    # must never stop esptool halfway through writing the chip
                    try:
                        on_line(text)
                    except Exception as e:  # noqa: BLE001
                        out.append(f"(progress report failed: {e})")
        p.wait()
    finally:
        killer.cancel()
    return p.returncode, "\n".join(out)[-3000:]


def flash(port=None, progress=None):
    """Compile the program for the XIAO and load it. Returns the log.
    `progress(stage, **kw)`, if given, hears each stage as it starts and
    the load's percentage as esptool reports it."""
    say = progress or (lambda stage, **kw: None)
    port = port or find_port()
    if not port:
        raise RuntimeError("no XIAO on USB: plug it in with a data cable")
    # the fingerprint rides in a header beside the program, so only the
    # program recompiles -- a define on the command line would change the
    # build's options and rebuild the whole ESP32 core every time
    with open(os.path.join(FIRMWARE, "fw_src.h"), "w") as f:
        f.write("// written by Load the program (tools/jig_control.py flash): the\n"
                "// fingerprint of orbital_jig.ino this build was made from\n"
                f"#define FW_SRC {source_print()}u\n")
    build = os.path.join(ROOT, "firmware", "build")
    out = []
    last = [-100]

    def heard(text):
        if "Connecting" in text and last[0] < 0:
            say("loading", what="connecting to the XIAO")
        m = re.search(r"Writing at .*?(\d+(?:\.\d+)?) ?%", text)
        if m:
            pct = int(float(m.group(1)))
            if pct >= last[0] + 2 or (pct == 100 and last[0] != 100):
                last[0] = pct
                say("loading", pct=pct)

    for stage, args in (("compiling", ["compile", "-b", FQBN, "--build-path", build, FIRMWARE]),
                        ("loading", ["upload", "-b", FQBN, "-p", port, "--input-dir", build, FIRMWARE])):
        say(stage)
        code, tail = _run_streaming(args, heard if stage == "loading" else (lambda t: None))
        out.append(tail)
        if code:
            raise RuntimeError("\n".join(out))
    return "\n".join(out)


# --- the two links ----------------------------------------------------------
class SimLink:
    """The simulator as a child process: program lines and '~' trace lines
    out, program commands and '#' controls in."""
    kind = "sim"

    def __init__(self, on_line, speed=1.0, bench=False, start_psi=None, extra=None):
        args = [build_sim()] + [f"--{k}={v}" for k, v in SPEC.items()]
        args += [f"--speed={speed}", f"--bench={1 if bench else 0}"]
        if start_psi is not None:
            args.append(f"--start_psi={start_psi}")
        for k, v in (extra or {}).items():
            args.append(f"--{k}={v}")
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, bufsize=1)
        self.on_line = on_line
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.on_line(line.rstrip("\n"))
        self.on_line("~{\"closed\":1}")

    def write(self, line):
        try:
            self.p.stdin.write(line + "\n")
            self.p.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
        try:
            self.p.stdout.close()
        except Exception:
            pass


class SerialLink:
    """The XIAO on its USB cable."""
    kind = "xiao"

    def __init__(self, on_line, port=None):
        import serial
        port = port or find_port()
        if not port:
            raise RuntimeError("no XIAO on USB: plug it in with a data cable")
        self.port = port
        self.s = serial.Serial(port, 115200, timeout=0.2)
        self.on_line = on_line
        self.alive = True
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        while self.alive:
            try:
                chunk = self.s.read(256)
            except Exception:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.on_line(line.decode("utf-8", "replace").rstrip("\r"))
        # closed by us, or gone from under us: unplugged, or reset by a load
        if self.alive:
            self.alive = False
            self.on_line("~{\"lost\":1}")

    def write(self, line):
        try:
            self.s.write((line + "\n").encode())
        except Exception:
            pass

    def close(self):
        self.alive = False
        try:
            self.s.close()
        except Exception:
            pass


# --- the jig ----------------------------------------------------------------
class Jig:
    """One controller, real or simulated, and the capture run on it.

    Everything the page shows is in `state()`; what happens is appended
    to a log and, from the simulator, a trace of every part. Both are
    numbered, so the page asks only for what it has not seen."""

    TRACE_KEEP = 30000          # samples: a minute at the simulator's 2 ms
    LOG_KEEP = 4000

    def __init__(self):
        self.lock = threading.RLock()
        self.link = None
        self.replies = queue.Queue()
        self.seq = 0
        self.log = deque(maxlen=self.LOG_KEEP)      # (seq, dict)
        self.trace = deque(maxlen=self.TRACE_KEEP)  # (seq, dict)
        self.dev = {}               # the program's last word on itself
        self.model = None
        self.phone = False
        self.run = None             # the capture's state, while there is one
        self.settings = dict(settle_s=1.0, after_shot_s=1.0)
        self._continue = threading.Event()
        self._abort = threading.Event()
        self.shots = []
        self.connected_as = None    # (mode, kw): what to reconnect after new code
        self.flashing = False
        self.board = None           # 'no program' or 'in loader', from its boot report
        self.resets = 0             # restarts seen while it has no program
        self._sent_at = self._answered_at = 0.0

    def idle(self):
        """Nothing under way that new code would cut short: no capture, no
        program being loaded, and the last command answered (or two minutes
        gone, the longest Home)."""
        running = self.run and self.run.get("state") not in ("done", "stopped", "failed")
        waiting = self._sent_at > self._answered_at and time.time() - self._sent_at < 120
        return not (running or self.flashing or waiting)

    def adopt(self, old):
        """Take over from a Jig made by the previous code: its log and its
        numbering, so the page carries on, and its connection, made again."""
        again = old.connected_as if old.link else None
        old.disconnect()            # first, so nothing it says is numbered after this
        with old.lock:
            self.seq, self.log, self.settings = old.seq, old.log, old.settings
        self._note("reloaded")
        if again:
            self.connect(again[0], **again[1])

    # the link
    def connect(self, mode="sim", **kw):
        self.disconnect()
        self._abort.clear()
        self.connected_as = (mode, dict(kw))
        with self.lock:
            self.shots = []
            self.model = None
            self.phone = False
            self.dev = {}
            self.board, self.resets = None, 0
            if mode == "sim":
                self.link = SimLink(self._line, **kw)
            else:
                self.link = SerialLink(self._line, port=kw.get("port"))
            self._note("connected", mode=mode,
                       port=getattr(self.link, "port", None))
        self.send("hello")

    def disconnect(self):
        self.abort()
        with self.lock:
            if self.link:
                self.link.close()
                self._note("disconnected")
            self.link = None

    def flash(self):
        """Load the program onto the XIAO. The upload needs the port, so a
        connection to the XIAO is let go first and made again after."""
        was = bool(self.link) and self.link.kind == "xiao"
        t0 = time.time()

        def say(stage, **kw):
            self._note("flash", stage=stage, t=round(time.time() - t0, 1), **kw)

        self.flashing = True
        if was:
            say("letting go of the port")
            self.disconnect()
        ok = False
        try:
            log = flash(progress=say)
            ok = True
            return log
        except Exception:
            say("failed")
            raise
        finally:
            if was:
                say("restarting")
                time.sleep(1.5)          # the XIAO restarting into the new program
                self.connect("xiao")
            self.flashing = False
            if ok:
                say("done")

    def _line(self, line):
        if not line:
            return
        with self.lock:
            self.seq += 1
            if line.startswith("~"):
                try:
                    d = json.loads(line[1:])
                except ValueError:
                    return
                if "model" in d:
                    self.model = d["model"]
                if "s" in d:
                    self.trace.append((self.seq, d))
                    return
                if "shot" in d:
                    self.shots.append(d)
                # the XIAO's port went away: say so, rather than go on taking
                # commands that reach nothing
                if d.get("lost") and self.link and not getattr(self.link, "alive", True):
                    self.link = None
                    self.seq += 1
                    self.log.append((self.seq, dict(ev="lost", src="mac")))
                    return
                self.log.append((self.seq, dict(d, src="sim")))
                return
            try:
                d = json.loads(line)
            except ValueError:
                d = dict(ev="text", text=line)
                if self._boot_report(line):
                    return
            else:
                self.board = None       # the program is talking: it runs
            if d.get("ev") == "hello":
                self.dev = d
                self.phone = d.get("phone", False)
            if d.get("ev") == "phone":
                self.phone = d.get("connected", False)
            self.log.append((self.seq, dict(d, src="xiao")))
        if d.get("ev") not in ("hall", "phone", "note", "text", "ble"):
            self._answered_at = time.time()
            self.replies.put(d)

    def _boot_report(self, line):
        """Read the board's boot report for whether it can run the program;
        True for a line to keep out of the log. The first time it has none,
        or is waiting in its loader, a note says what to do, once."""
        if NO_PROGRAM.search(line):
            if "No bootable" in line:
                self.resets += 1
            if self.board != "no program":
                self.board = "no program"
                self._note("board", state=self.board)
            return True
        if IN_LOADER.search(line):
            if self.board != "in loader":
                self.board = "in loader"
                self._note("board", state=self.board)
            return False
        return self.board == "no program" and bool(BOOT_REPORT.search(line))

    def _note(self, ev, /, **kw):
        # `ev` positional-only: a note may carry its own `what` (a load
        # stage does), and a keyword of the same name collided with it --
        # which failed a load halfway and left the XIAO in its bootloader
        with self.lock:
            self.seq += 1
            self.log.append((self.seq, dict(kw, ev=ev, src="mac")))

    def send(self, line):
        if not self.link:
            raise RuntimeError("not connected")
        # a hello moves nothing, and a board with no program never answers
        # it: it must not hold back new code for two minutes (idle())
        if line != "hello":
            self._sent_at = time.time()
        with self.lock:
            self.seq += 1
            self.log.append((self.seq, dict(ev="sent", src="mac", line=line)))
        self.link.write(line)

    def control(self, line):
        """A '#' control for the simulator: #speed 4, #drag 0.5, #jam ..."""
        if self.link and self.link.kind == "sim":
            self.link.write("#" + line)

    def ask(self, line, until, timeout):
        """Send a command and wait for its answer: the first reply `until`
        accepts, or an error."""
        while not self.replies.empty():
            self.replies.get_nowait()
        self.send(line)
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise RuntimeError(f"no answer to '{line}'")
            if self._abort.is_set():
                raise RuntimeError("stopped")
            try:
                d = self.replies.get(timeout=min(left, 0.2))
            except queue.Empty:
                continue
            if d.get("ev") == "error":
                raise RuntimeError(d.get("what", "error"))
            if until(d):
                return d

    # the capture
    def start_capture(self, rings=None):
        with self.lock:
            if self.run and self.run.get("state") not in ("done", "failed", "stopped"):
                raise RuntimeError("a capture is already running")
            self._abort.clear()
            self._continue.clear()
            self.shots = []
            self.run = dict(state="starting", ring=None, frame=0, frames=sum(r["frames"] for r in RINGS),
                            done=0, message="", started=time.time(), rings=rings or [r["ring"] for r in RINGS])
        threading.Thread(target=self._capture, daemon=True).start()

    def proceed(self):
        self._continue.set()

    def abort(self):
        self._abort.set()
        self._continue.set()
        if self.link:
            self.link.write("stop")

    def _set(self, **kw):
        with self.lock:
            self.run.update(kw)
            self.seq += 1
            self.log.append((self.seq, dict(ev="run", src="mac", **kw)))

    def _wait_continue(self):
        self._continue.clear()
        while not self._continue.wait(0.2):
            pass
        if self._abort.is_set():
            raise RuntimeError("stopped")

    def _sleep(self, s):
        if self._abort.wait(s):
            raise RuntimeError("stopped")

    def _capture(self):
        speed = 1.0
        try:
            self._set(state="checking", message="Asking the controller what it is")
            self.ask("hello", lambda d: d.get("ev") == "hello", 5)
            if not self.phone:
                self._set(state="phone", message="Waiting for the phone: Settings, Bluetooth, "
                                                 "'Orbital Jig' -- and the Camera app open")
                while not self.phone:
                    self._sleep(0.2)
            self._set(state="homing", message="Finding home: up to 36 turns")
            self.ask("home", lambda d: d.get("ev") == "homed", 90)
            done = 0
            for r in RINGS:
                if r["ring"] not in self.run["rings"]:
                    continue
                self._set(state="elevation", ring=r["ring"], frame=0,
                          message=f"Set the carriage to {r['elev']:g}° "
                                  f"(ring {r['ring']}, {r['name']}), tighten the thumbscrew, then Continue")
                self._wait_continue()
                for f in range(r["frames"]):
                    self._set(state="frame", ring=r["ring"], frame=f + 1,
                              message=f"Ring {r['ring']}, frame {f + 1} of {r['frames']}")
                    self._sleep(self.settings["settle_s"] / speed)
                    self.ask("shoot", lambda d: d.get("ev") == "shot", 5)
                    done += 1
                    self._set(done=done)
                    self._sleep(self.settings["after_shot_s"] / speed)
                    d = self.ask(f"step {r['stops']}", lambda d: d.get("ev") == "stepped",
                                 10 + 3 * r["stops"])
                    if d.get("hall") != d.get("home_expected"):
                        raise RuntimeError(
                            f"the home switch says {'home' if d.get('hall') else 'not home'} at stop "
                            f"{d.get('stop')}, where the counts say "
                            f"{'home' if d.get('home_expected') else 'not home'}: "
                            "something slipped -- the set screw on the motor's shaft first")
                    chk = d.get("home_check_deg")
                    if chk is not None and abs(chk) > 40:
                        raise RuntimeError(
                            f"passing home, the lock's centre was {chk:.0f}° of the driver's turn "
                            "from where the counts put it: the set screw on the motor's shaft has slipped")
            self._set(state="done", message=f"Done: {done} frames")
        except Exception as e:  # noqa: BLE001 -- every failure ends the run, and says why
            stopped = self._abort.is_set()      # Stop pressed: whatever the program said about it
            if self.link:
                self.link.write("stop")
            self._set(state="stopped" if stopped else "failed", message=str(e))

    # what the page reads
    def state(self, since=0, trace_since=None):
        with self.lock:
            ts = since if trace_since is None else trace_since
            return dict(
                connected=bool(self.link),
                mode=self.link.kind if self.link else None,
                port=getattr(self.link, "port", None),
                dev=self.dev, src=source_print(), boot=BOOT,
                model=self.model, phone=self.phone,
                board=self.board, resets=self.resets,
                run=self.run, settings=self.settings, seq=self.seq,
                log=[dict(d, seq=s) for s, d in self.log if s > since],
                trace=[dict(d, seq=s) for s, d in self.trace if s > ts],
            )


def main(argv):
    if argv and argv[0] == "flash":
        print(flash())
        return 0
    mode = argv[0] if argv else "sim"
    jig = Jig()
    jig.connect(mode, speed=0) if mode == "sim" else jig.connect(mode)
    time.sleep(0.5)
    for cmd in argv[1:]:
        word = cmd.split()[0]
        want = dict(spin="done", home="homed", step="stepped", shoot="shot", hello="hello",
                    hall="hall").get(word, "")
        d = jig.ask(cmd, lambda d: d.get("ev") == want, 120)
        print(json.dumps(d))
    jig.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
