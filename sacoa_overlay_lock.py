# sacoa_overlay_lock.py  (v1.1 – fixed colors, Sacoa serial trigger + blur overlay)
# - Fullscreen blur overlay met meertalige boodschap
# - Geen keypad/tekstveld
# - Luistert op seriële poort; bij trigger -> overlay weg; auto-relock na X seconden

import tkinter as tk
import ctypes
from ctypes import wintypes
import sys
import threading
import time
from pathlib import Path

# === CONFIG ===
SCREEN_INDEX = 0                 # 0=primair, 1=tweede, 2=derde monitor
AUTO_RELOCK_SECONDS = 90         # na hoeveel seconden de overlay automatisch terugkomt (0 = nooit)
COM_PORT = "COM5"                # pas aan naar je seriële poort
BAUDRATE = 9600                  # baudrate van je ESP32
TRIGGER_MIN_INTERVAL = 1.0       # minimale tijd tussen triggers (anti-spam)

# Blur & uiterlijk
BLUR_RADIUS = 12
DIM_ALPHA = 0.35
BG_FALLBACK = "#111122"
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 22)

# === DEPENDENCIES ===
# pip install pillow pyserial
try:
    from PIL import ImageGrab, ImageFilter, Image, ImageTk
    has_pillow = True
except Exception:
    has_pillow = False

try:
    import serial
    import serial.tools.list_ports
    has_serial = True
except Exception:
    has_serial = False

# === Windows monitor info via Win32 ===
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(wintypes.RECT), ctypes.c_double
)
_monitors = []
def _monitor_enum(hMonitor, hdcMonitor, lprcMonitor, dwData):
    r = lprcMonitor.contents
    _monitors.append((r.left, r.top, r.right, r.bottom))
    return 1

def get_monitors():
    _monitors.clear()
    user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_monitor_enum), 0)
    return _monitors[:]

class SacoaOverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        screens = get_monitors()
        if not screens:
            tk.messagebox.showerror("Overlay", "Geen schermen gevonden.")
            sys.exit(1)

        self.screen_idx = SCREEN_INDEX if 0 <= SCREEN_INDEX < len(screens) else 0
        self.sx, self.sy, self.sr, self.sb = screens[self.screen_idx]
        self.swidth  = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self.overlay = None
        self.img_ref = None
        self.last_trigger = 0.0
        self.relock_timer = None

        self._build_overlay()
        self.show_overlay()

        if has_serial:
            t = threading.Thread(target=self._serial_loop, daemon=True)
            t.start()

    # ---- overlay bouwen ----
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        # achtergrond label (voor blur image)
        self.bg_label = tk.Label(self.overlay, bg=BG_FALLBACK)
        self.bg_label.pack(fill="both", expand=True)

        # tekst container
        self.text_frame = tk.Frame(self.bg_label, bg=BG_FALLBACK, highlightthickness=0)
        self.text_frame.place(relx=0.5, rely=0.5, anchor="center")

        title = tk.Label(self.text_frame,
                         text="Scan uw pasje om te activeren",
                         font=TITLE_FONT, fg="white", bg=BG_FALLBACK)
        title.pack(pady=(0, 10))

        sub_en = tk.Label(self.text_frame,
                          text="Scan your card to activate",
                          font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK)
        sub_en.pack()

        sub_de = tk.Label(self.text_frame,
                          text="Bitte Karte scannen zum Aktivieren",
                          font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK)
        sub_de.pack()

    # ---- blur achtergrond ----
    def _render_blur(self):
        if not has_pillow:
            self.bg_label.configure(bg=BG_FALLBACK, image="")
            self.img_ref = None
            return
        try:
            img = ImageGrab.grab(bbox=(self.sx, self.sy, self.sr, self.sb))
            img = img.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
            if DIM_ALPHA > 0:
                black = Image.new("RGB", img.size, (0, 0, 0))
                img = Image.blend(img, black, DIM_ALPHA)
            tkimg = ImageTk.PhotoImage(img)
            self.img_ref = tkimg
            self.bg_label.configure(image=self.img_ref, bg="")
        except Exception:
            self.bg_label.configure(bg=BG_FALLBACK, image="")
            self.img_ref = None

    # ---- overlay tonen/verbergen ----
    def show_overlay(self):
        self._render_blur()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)

    def hide_overlay(self):
        self.overlay.withdraw()

    # ---- seriële triggers ----
    def on_serial_trigger(self):
        now = time.time()
        if now - self.last_trigger < TRIGGER_MIN_INTERVAL:
            return
        self.last_trigger = now

        # Overlay verbergen
        self.hide_overlay()

        # Auto-relock timer
        if self.relock_timer:
            try:
                self.relock_timer.cancel()
            except Exception:
                pass
            self.relock_timer = None

        if AUTO_RELOCK_SECONDS > 0:
            self.relock_timer = threading.Timer(AUTO_RELOCK_SECONDS, self._relock)
            self.relock_timer.daemon = True
            self.relock_timer.start()

    def _relock(self):
        self.root.after(0, self.show_overlay)

    # ---- seriële lees-loop ----
    def _serial_loop(self):
        ser = None
        while True:
            try:
                if ser is None or not ser.is_open:
                    try:
                        ser = serial.Serial(COM_PORT, BAUDRATE, timeout=0.2)
                    except Exception:
                        time.sleep(1.0)
                        continue

                data = ser.readline()
                if data:
                    line = data.decode(errors="ignore").strip()
                    if line:
                        self.root.after(0, self.on_serial_trigger)
                        time.sleep(0.1)
                else:
                    b = ser.read(1)
                    if b:
                        self.root.after(0, self.on_serial_trigger)
                        time.sleep(0.1)

            except Exception:
                try:
                    if ser:
                        ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(1.0)

def main():
    root = tk.Tk()
    app = SacoaOverlayApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
