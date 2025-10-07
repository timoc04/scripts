# sacoa_overlay_lock.py  (v1.2 – fixed: geen alpha in bg-kleuren)
# - Fullscreen blur overlay met meertalige tekst
# - Geen keypad/tekstveld
# - Seriële trigger (ESP32/adapter) verbergt overlay; auto-relock na X sec

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import threading
import time

# ====== CONFIG ======
SCREEN_INDEX = 0                 # 0=primair, 1=tweede, 2=derde monitor
AUTO_RELOCK_SECONDS = 90         # 0 = nooit automatisch relocken
COM_PORT = "COM5"                # pas aan naar jouw COM-poort
BAUDRATE = 9600
TRIGGER_MIN_INTERVAL = 1.0       # anti-spam (sec)

# Uiterlijk/blur
BLUR_RADIUS = 12
DIM_ALPHA = 0.35                 # extra verdonkeren 0..1
BG_FALLBACK = "#111122"          # effen fallback-kleur
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 22)

# ====== DEPENDENCIES ======
# pip install pillow pyserial
try:
    from PIL import ImageGrab, ImageFilter, Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    import serial
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

# ====== MONITOR INFO (Win32) ======
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

# ====== APP ======
class SacoaOverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        screens = get_monitors()
        if not screens:
            messagebox.showerror("Overlay", "Geen schermen gevonden.")
            raise SystemExit(1)

        self.sx, self.sy, self.sr, self.sb = screens[min(max(0, SCREEN_INDEX), len(screens)-1)]
        self.swidth  = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self.overlay = None
        self.img_ref = None
        self.last_trigger = 0.0
        self.relock_timer = None

        self._build_overlay()
        self.show_overlay()

        if HAS_SERIAL:
            t = threading.Thread(target=self._serial_loop, daemon=True)
            t.start()

    # ---- UI ----
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        # Achtergrondbeeld (blur) of effen kleur
        self.bg_label = tk.Label(self.overlay, bg=BG_FALLBACK)
        self.bg_label.pack(fill="both", expand=True)

        # Tekstcontainer (géén alpha: gebruik effen bg)
        self.text_frame = tk.Frame(self.bg_label, bg=BG_FALLBACK, highlightthickness=0)
        self.text_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.text_frame,
                 text="Scan uw pasje om te activeren",
                 font=TITLE_FONT, fg="white", bg=BG_FALLBACK).pack(pady=(0, 10))

        tk.Label(self.text_frame,
                 text="Scan your card to activate",
                 font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK).pack()

        tk.Label(self.text_frame,
                 text="Bitte Karte scannen zum Aktivieren",
                 font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK).pack()

    def _render_blur(self):
        if not HAS_PIL:
            self.bg_label.configure(bg=BG_FALLBACK, image="")
            self.img_ref = None
            return
        try:
            img = ImageGrab.grab(bbox=(self.sx, self.sy, self.sr, self.sb))
            img = img.filter(ImageFilter.GaussianBlur(blur := BLUR_RADIUS))
            if DIM_ALPHA > 0:
                black = Image.new("RGB", img.size, (0, 0, 0))
                img = Image.blend(img, black, DIM_ALPHA)
            tkimg = ImageTk.PhotoImage(img)
            self.img_ref = tkimg
            self.bg_label.configure(image=self.img_ref, bg="black")  # geen alpha gebruiken
        except Exception:
            self.bg_label.configure(bg=BG_FALLBACK, image="")
            self.img_ref = None

    def show_overlay(self):
        self._render_blur()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)

    def hide_overlay(self):
        self.overlay.withdraw()

    # ---- Trigger vanuit serieel ----
    def on_serial_trigger(self):
        now = time.time()
        if now - self.last_trigger < TRIGGER_MIN_INTERVAL:
            return
        self.last_trigger = now

        self.hide_overlay()

        if self.relock_timer:
            try:
                self.relock_timer.cancel()
            except Exception:
                pass
            self.relock_timer = None

        if AUTO_RELOCK_SECONDS > 0:
            self.relock_timer = threading.Timer(AUTO_RELOCK_SECONDS, lambda: self.root.after(0, self.show_overlay))
            self.relock_timer.daemon = True
            self.relock_timer.start()

    # ---- Seriële lees-loop ----
    def _serial_loop(self):
        import serial  # safe import hier
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
                if data and data.strip():
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
