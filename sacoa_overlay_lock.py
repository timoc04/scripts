# sacoa_overlay_lock.py  (v1.3.2 – Service-knop ín de overlay + numpad 1423)
# - Blur overlay met NL/EN/DE tekst
# - Seriële trigger (ESP32) ontgrendelt; auto-relock na X sec
# - Service-knop rechtsonder in de overlay; toont numpad; PIN 1423 ontgrendelt

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import threading
import time

# ====== CONFIG ======
SCREEN_INDEX = 0
AUTO_RELOCK_SECONDS = 90
COM_PORT = "COM5"
BAUDRATE = 9600
TRIGGER_MIN_INTERVAL = 1.0

SERVICE_PIN = "1423"

# UI
BLUR_RADIUS = 12
DIM_ALPHA = 0.35
BG_FALLBACK = "#111122"
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 22)

SERVICE_W, SERVICE_H = 150, 45
SERVICE_MARGIN = 40

# ====== deps ======
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

# ====== monitor info ======
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
            messagebox.showerror("Overlay", "Geen schermen gevonden.")
            raise SystemExit(1)
        idx = min(max(0, SCREEN_INDEX), len(screens)-1)
        self.sx, self.sy, self.sr, self.sb = screens[idx]
        self.swidth  = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self.overlay = None
        self.bg_label = None
        self.img_ref = None
        self.last_trigger = 0.0
        self.relock_timer = None

        self.keypad_win = None
        self.entered = ""
        self.mask_var = None

        self._build_overlay()
        self.show_overlay()

        if HAS_SERIAL:
            threading.Thread(target=self._serial_loop, daemon=True).start()

    # ---------- overlay ----------
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        # achtergrond voor blur
        self.bg_label = tk.Label(self.overlay, bg=BG_FALLBACK)
        self.bg_label.pack(fill="both", expand=True)

        # tekst in het midden
        text_frame = tk.Frame(self.overlay, bg=BG_FALLBACK, highlightthickness=0)
        text_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(text_frame, text="Scan uw pasje om te activeren",
                 font=TITLE_FONT, fg="white", bg=BG_FALLBACK).pack(pady=(0, 10))
        tk.Label(text_frame, text="Scan your card to activate",
                 font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK).pack()
        tk.Label(text_frame, text="Bitte Karte scannen zum Aktivieren",
                 font=SUB_FONT, fg="#DDDDFF", bg=BG_FALLBACK).pack()

        # SERVICE-knop RECHTSONDER (in overlay zelf, dus altijd zichtbaar binnen de overlay)
        self.service_btn = tk.Button(
            self.overlay, text="Service", font=("Segoe UI", 11, "bold"),
            bg="#F2F2F7", activebackground="#E6E6EC", relief="raised",
            command=self._on_service_pressed
        )
        # vaste afmeting + positionering t.o.v. rechter/onderrand
        self.service_btn.place(
            x=self.swidth - SERVICE_MARGIN, y=self.sheight - SERVICE_MARGIN,
            anchor="se", width=SERVICE_W, height=SERVICE_H
        )

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
            self.img_ref = ImageTk.PhotoImage(img)
            self.bg_label.configure(image=self.img_ref, bg="black")
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

    # ---------- service / keypad ----------
    def _on_service_pressed(self):
        self._show_keypad()

    def _show_keypad(self):
        if self.keypad_win and self.keypad_win.winfo_exists():
            self.keypad_win.deiconify()
            self.keypad_win.lift()
            self.keypad_win.focus_set()
            return

        self.keypad_win = tk.Toplevel(self.root)
        self.keypad_win.attributes("-topmost", True)
        self.keypad_win.title("Service")
        kw, kh = 380, 520
        kx = self.sx + (self.swidth - kw) // 2
        ky = self.sy + (self.sheight - kh) // 2
        self.keypad_win.geometry(f"{kw}x{kh}+{kx}+{ky}")
        self.keypad_win.configure(bg=BG_FALLBACK)

        self.mask_var = tk.StringVar(value="")
        tk.Label(self.keypad_win, textvariable=self.mask_var,
                 font=("Segoe UI", 28), bg="#22223A", fg="white",
                 width=20, height=2).pack(pady=(12, 8))

        frame_keys = tk.Frame(self.keypad_win, bg=BG_FALLBACK); frame_keys.pack(pady=8)
        btn_cfg = {"font":("Segoe UI", 20), "width":6, "height":3}
        labels = [["1","2","3"], ["4","5","6"], ["7","8","9"], ["Wissen","0","⌫"]]
        for row in labels:
            r = tk.Frame(frame_keys, bg=BG_FALLBACK); r.pack()
            for lab in row:
                tk.Button(r, text=lab, command=lambda x=lab: self._keypad_press(x), **btn_cfg)\
                    .pack(side="left", padx=6, pady=6)

        tk.Button(self.keypad_win, text="ONTGRENDEL",
                  font=("Segoe UI", 18, "bold"),
                  bg="#3A6FF2", fg="white",
                  command=self._keypad_try_unlock, width=30, height=2).pack(pady=(12,14))

        tk.Button(self.keypad_win, text="Sluiten", command=self._close_keypad)\
            .place(x=kw-80, y=12)

        self.keypad_win.focus_set()

    def _keypad_press(self, lab):
        if lab == "Wissen":
            self.entered = ""
        elif lab == "⌫":
            self.entered = self.entered[:-1]
        else:
            if len(self.entered) < 32:
                self.entered += lab
        self.mask_var.set("•" * len(self.entered) if self.entered else "")

    def _keypad_try_unlock(self):
        if self.entered == SERVICE_PIN:
            self.entered = ""
            self.mask_var.set("")
            self.hide_overlay()
            self._close_keypad()
            if self.relock_timer:
                try: self.relock_timer.cancel()
                except Exception: pass
            self.relock_timer = None
        else:
            prev = self.mask_var.get()
            self.mask_var.set("Foutieve code")
            self.keypad_win.after(900, lambda: self.mask_var.set(prev))
            self.entered = ""

    def _close_keypad(self):
        if self.keypad_win and self.keypad_win.winfo_exists():
            self.keypad_win.withdraw()

    # ---------- serial ----------
    def on_serial_trigger(self):
        now = time.time()
        if now - self.last_trigger < TRIGGER_MIN_INTERVAL:
            return
        self.last_trigger = now
        self.hide_overlay()
        if self.relock_timer:
            try: self.relock_timer.cancel()
            except Exception: pass
        self.relock_timer = None
        if AUTO_RELOCK_SECONDS > 0:
            self.relock_timer = threading.Timer(AUTO_RELOCK_SECONDS, lambda: self.root.after(0, self.show_overlay))
            self.relock_timer.daemon = True
            self.relock_timer.start()

    def _serial_loop(self):
        import serial
        ser = None
        while True:
            try:
                if ser is None or not ser.is_open:
                    try:
                        ser = serial.Serial(COM_PORT, BAUDRATE, timeout=0.2)
                    except Exception:
                        time.sleep(1.0); continue
                data = ser.readline()
                if data and data.strip():
                    self.root.after(0, self.on_serial_trigger); time.sleep(0.1)
                else:
                    b = ser.read(1)
                    if b: self.root.after(0, self.on_serial_trigger); time.sleep(0.1)
            except Exception:
                try:
                    if ser: ser.close()
                except Exception: pass
                ser = None
                time.sleep(1.0)

def main():
    root = tk.Tk()
    app = SacoaOverlayApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
