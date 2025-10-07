# sacoa_overlay_lock.py  (v1.3 – Service-knop + Numpad (code 1423) + serial trigger + blur)
# - Rechtsonder: "Service" knop (altijd zichtbaar)
# - Numpad verschijnt bij Service; code 1423 ontgrendelt overlay
# - Blur overlay met meertalige tekst
# - Luistert op seriële poort (ESP32) voor trigger; auto-relock na X seconden

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import threading
import time

# ====== CONFIG ======
SCREEN_INDEX = 0                 # 0=primair, 1=tweede, ...
AUTO_RELOCK_SECONDS = 90         # 0 = nooit automatisch relocken
COM_PORT = "COM5"                # pas aan naar jouw COM-poort
BAUDRATE = 9600
TRIGGER_MIN_INTERVAL = 1.0       # anti-spam (sec)

# Service PIN (numpad)
SERVICE_PIN = "1423"

# Uiterlijk/blur
BLUR_RADIUS = 12
DIM_ALPHA = 0.35                 # extra verdonkeren 0..1
BG_FALLBACK = "#111122"          # effen fallback-kleur
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 22)

# Service-knop grootte/marge
SERVICE_W, SERVICE_H = 150, 45
SERVICE_MARGIN = 40

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

        idx = min(max(0, SCREEN_INDEX), len(screens)-1)
        self.sx, self.sy, self.sr, self.sb = screens[idx]
        self.swidth  = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self.overlay = None
        self.img_ref = None
        self.last_trigger = 0.0
        self.relock_timer = None

        # service button window & keypad
        self.service_win = None
        self.keypad_win = None
        self.entered = ""

        self._build_overlay()
        self._build_service_button()
        self.show_overlay()

        if HAS_SERIAL:
            t = threading.Thread(target=self._serial_loop, daemon=True)
            t.start()

    # ---- UI overlay ----
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        self.bg_label = tk.Label(self.overlay, bg=BG_FALLBACK)
        self.bg_label.pack(fill="both", expand=True)

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
            img = img.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
            if DIM_ALPHA > 0:
                black = Image.new("RGB", img.size, (0, 0, 0))
                img = Image.blend(img, black, DIM_ALPHA)
            tkimg = ImageTk.PhotoImage(img)
            self.img_ref = tkimg
            self.bg_label.configure(image=self.img_ref, bg="black")
        except Exception:
            self.bg_label.configure(bg=BG_FALLBACK, image="")
            self.img_ref = None

    def show_overlay(self):
        self._render_blur()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)
        # zorg dat service-knop bovenop blijft
        self._show_service_button()

    def hide_overlay(self):
        self.overlay.withdraw()

    # ---- Service knop (rechtsonder) ----
    def _build_service_button(self):
        if self.service_win and self.service_win.winfo_exists():
            return

        self.service_win = tk.Toplevel(self.root)
        self.service_win.overrideredirect(True)
        self.service_win.attributes("-topmost", True)
        self.service_win.configure(bg="#F2F2F7")

        btn = tk.Button(
            self.service_win, text="Service", font=("Segoe UI", 11, "bold"),
            width=12, height=2, command=self._on_service_pressed,
            relief="raised", bg="#F2F2F7", activebackground="#E6E6EC"
        )
        btn.pack()
        self._place_service_button()

        # als het venster gemi
