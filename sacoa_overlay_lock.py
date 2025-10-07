# sacoa_overlay_lock.py (v1.3.8 – egaal geblurd, geen donker vlak achter tekst)
# Overlay met blur en meertalige tekst
# Seriële trigger via ESP32
# Service-knop met toetsenbord/numpad
# Volledig fullscreen blur zonder kleurvlakken

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import threading, time

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
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 22)
SERVICE_W, SERVICE_H = 150, 45
SERVICE_MARGIN = 40

# ====== DEPS ======
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

# ====== MONITOR HELPERS ======
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

    # ---------- OVERLAY ----------
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        # achtergrond met blur
        self.bg_label = tk.Label(self.overlay)
        self.bg_label.pack(fill="both", expand=True)

        # tekst direct op blur (geen achtergrondvlak)
        text_frame = tk.Frame(self.overlay, bg="", highlightthickness=0)
        text_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(text_frame, text="Scan uw pasje om te activeren",
                 font=TITLE_FONT, fg="white", bg="").pack(pady=(0, 10))
        tk.Label(text_frame, text="Scan your card to activate",
                 font=SUB_FONT, fg="#DDDDFF", bg="").pack()
        tk.Label(text_frame, text="Bitte Karte scannen zum Aktivieren",
                 font=SUB_FONT, fg="#DDDDFF", bg="").pack()

        # Service-knop rechtsonder
        self.service_btn = tk.Button(
            self.overlay, text="Service", font=("Segoe UI", 11, "bold"),
            bg="#F2F2F7", activebackground="#E6E6EC", relief="raised",
            command=self._on_service_pressed
        )
        self.service_btn.place(
            x=self.swidth - SERVICE_MARGIN, y=self.sheight - SERVICE_MARGIN,
            anchor="se", width=SERVICE_W, height=SERVICE_H
        )

    def _render_blur(self):
        if not HAS_PIL:
            self.bg_label.configure(bg="black", image="")
            self.img_ref = None
            return
        try:
            img = ImageGrab.grab(bbox=(self.sx, self.sy, self.sr, self.sb))
            img = img.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
            if DIM_ALPHA > 0:
                black = Image.new("RGB", img.size, (0, 0, 0))
                img = Image.blend(img, black, DIM_ALPHA)
            self.img_ref = ImageTk.PhotoImage(img)
            self.bg_label.configure(image=self.img_ref)
        except Exception:
            self.bg_label.configure(bg="black", image="")
            self.img_ref = None

    def show_overlay(self):
        self._render_blur()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)

    def hide_overlay(self):
        self.overlay.withdraw()

    # ---------- SERVICE / KEYPAD ----------
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
        kw, kh = 420, 520
        kx = self.sx + (self.swidth - kw) // 2
        ky = self.sy + (self.sheight - kh) // 2
        self.keypad_win.geometry(f"{kw}x{kh}+{kx}+{ky}")
        self.keypad_win.configure(bg="#111122")
        self.keypad_win.resizable(False, False)

        self.mask_var = tk.StringVar(value="")
        tk.Label(self.keypad_win, textvariable=self.mask_var,
                 font=("Segoe UI", 22), bg="#22223A", fg="white",
                 width=22, height=1).pack(pady=(10, 6))

        grid = tk.Frame(self.keypad_win, bg="#111122")
        grid.pack(pady=6)

        btn_font = ("Segoe UI", 18)
        btn_w, btn_h = 6, 1
        pad = dict(padx=6, pady=6)

        labels = [
            ["1","2","3"],
            ["4","5","6"],
            ["7","8","9"],
            ["Wissen","0","⌫"]
        ]
        for r, row in enumerate(labels):
            for c, lab in enumerate(row):
                tk.Button(grid, text=lab, font=btn_font, width=btn_w, height=btn_h,
                          command=lambda x=lab: self._keypad_press(x))\
                    .grid(row=r, column=c, **pad)

        tk.Button(self.keypad_win, text="ONTGRENDEL",
                  font=("Segoe UI", 18, "bold"), bg="#3A6FF2", fg="white",
                  command=self._keypad_try_unlock)\
            .pack(fill="x", padx=16, pady=(8, 10))

        self.keypad_win.bind("<Key>", self._kb_type)
        self.keypad_win.bind("<BackSpace>", self._kb_backspace)
        self.keypad_win.bind("<Escape>", self._kb_clear)
        self.keypad_win.bind("<Return>", lambda e: self._keypad_try_unlock())
        self.keypad_win.focus_set()

    def _kb_type(self, event):
        ch = event.char
        if ch and ch.isdigit():
            if len(self.entered) < 32:
                self.entered += ch
                self.mask_var.set("•"*len(self.entered))

    def _kb_backspace(self, event):
        if self.entered:
            self.entered = self.entered[:-1]
            self.mask_var.set("•"*len(self.entered) if self.entered else "")

    def _kb_clear(self, event):
        self.entered = ""
        self.mask_var.set("")

    def _keypad_press(self, lab):
        if lab == "Wissen":
            self.entered = ""
        elif lab == "⌫":
            self.entered = self.entered[:-1]
        else:
            if len(self.entered) < 32:
                self.entered += lab
        self.mask_var.set("•"*len(self.entered) if self.entered else "")

    def _keypad_try_unlock(self):
        if self.entered == SERVICE_PIN:
            self.entered = ""
            self.mask_var.set("")
            self.hide_overlay()
            if self.keypad_win and self.keypad_win.winfo_exists():
                self.keypad_win.withdraw()
            if self.relock_timer:
                try: self.relock_timer.cancel()
                except Exception: pass
            self.relock_timer = None
        else:
            self.mask_var.set("Foutieve code")
            self.keypad_win.after(900, lambda: self.mask_var.set(""))
            self.entered = ""

    # ---------- SERIAL ----------
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
            self.relock_timer = threading.Timer(
                AUTO_RELOCK_SECONDS, lambda: self.root.after(0, self.show_overlay)
            )
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
                    if b:
                        self.root.after(0, self.on_serial_trigger); time.sleep(0.1)
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
