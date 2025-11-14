r"""
sacoa_overlay_lock.py

Benodigd op een nieuwe PC:
1) Open CMD en voer uit:
   winget install Python.Python.3.12
2) Open CMD en voer uit:
   pip install pillow pyserial

Starttips:
- Start met:  pythonw sacoa_overlay_lock.py   (geen consolevenster)
- Taakplanner: Programma/script = <pad>\pythonw.exe, Argumenten = <pad>\sacoa_overlay_lock.py, Beginnen in = C:\<pad>
"""

import tkinter as tk
from tkinter import messagebox
import ctypes, sys
from ctypes import wintypes
import threading, time

# ========= INSTELLINGEN =========
SCREEN_INDEX = 0                  # 0 = primair, 1 = tweede, etc.
START_LOCK_DELAY_SECONDS = 60     # overlay pas na X seconden tonen
AUTO_RELOCK_SECONDS = 240         # na ontgrendelen automatisch weer locken
COM_PORT = "COM10"                # seriële poort van ESP32/adapter (in device manager als vaste poort instellen)
BAUDRATE = 9600
TRIGGER_MIN_INTERVAL = 1.0        # debounce tegen meerdere pulsen
SERVICE_PIN = "1423"              # code via Service-venster

# UI
BLUR_RADIUS = 12
DIM_ALPHA = 0.35
TITLE_FONT = ("Segoe UI", 40, "bold")
SUB_FONT   = ("Segoe UI", 30)
SERVICE_W, SERVICE_H = 150, 45
SERVICE_MARGIN = 40

# ========= DEPENDENCIES =========
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

# ========= MONITOR HELPERS =========
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

# ========= APP =========
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
        self.canvas  = None
        self.img_ref = None
        self.last_trigger = 0.0
        self.relock_timer = None

        self.keypad_win = None
        self.entered = ""
        self.mask_var = None

        self._build_overlay()

        # Overlay pas na START_LOCK_DELAY_SECONDS tonen
        threading.Timer(
            START_LOCK_DELAY_SECONDS, lambda: self.root.after(0, self.show_overlay)
        ).start()

        if HAS_SERIAL:
            threading.Thread(target=self._serial_loop, daemon=True).start()

    # ----- Overlay -----
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        self.canvas = tk.Canvas(self.overlay, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # Service-knop (rechts onder)
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
        """Maak screenshot van het scherm, blur en dim ‘m, en teken de teksten erop."""
        if not HAS_PIL:
            self.canvas.configure(bg="black"); self.canvas.delete("all")
            return
        try:
            img = ImageGrab.grab(bbox=(self.sx, self.sy, self.sr, self.sb))
            img = img.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
            if DIM_ALPHA > 0:
                black = Image.new("RGB", img.size, (0,0,0))
                img = Image.blend(img, black, DIM_ALPHA)
            self.img_ref = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.img_ref)
            cx, cy = self.swidth//2, self.sheight//2
            self.canvas.create_text(cx, cy-40,
                                    text="Scan uw pasje om te activeren",
                                    fill="white", font=TITLE_FONT, anchor="s")
            self.canvas.create_text(cx, cy-25,
                                    text="Scan your card to activate",
                                    fill="#DDDDFF", font=SUB_FONT, anchor="n")
            self.canvas.create_text(cx, cy+25,
                                    text="Bitte Karte scannen zum Aktivieren",
                                    fill="#DDDDFF", font=SUB_FONT, anchor="n")
        except Exception:
            self.canvas.configure(bg="black"); self.canvas.delete("all")

    def show_overlay(self):
        self._render_blur()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)
        try: self.canvas.focus_set()
        except Exception: pass

    def hide_overlay(self):
        self.overlay.withdraw()

    # ----- Relock -----
    def _start_relock_timer(self):
        """Start/Herstart de timer die na AUTO_RELOCK_SECONDS de overlay terugplaatst."""
        if self.relock_timer:
            try: self.relock_timer.cancel()
            except Exception: pass
        self.relock_timer = threading.Timer(
            AUTO_RELOCK_SECONDS, lambda: self.root.after(0, self.show_overlay)
        )
        self.relock_timer.daemon = True
        self.relock_timer.start()

    # ----- Service / keypad -----
    def _on_service_pressed(self):
        self._show_keypad()

    def _show_keypad(self):
        if self.keypad_win and self.keypad_win.winfo_exists():
            self.keypad_win.deiconify(); self.keypad_win.lift(); self.keypad_win.focus_set()
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
        self.keypad_win.protocol("WM_DELETE_WINDOW", self._on_keypad_close)

        self.mask_var = tk.StringVar(value="")
        tk.Label(self.keypad_win, textvariable=self.mask_var,
                 font=("Segoe UI", 22), bg="#22223A", fg="white",
                 width=22, height=1).pack(pady=(10, 6))

        grid = tk.Frame(self.keypad_win, bg="#111122"); grid.pack(pady=6)
        btn_font = ("Segoe UI", 18); btn_w, btn_h = 6, 1; pad = dict(padx=6, pady=6)
        labels = [["1","2","3"], ["4","5","6"], ["7","8","9"], ["Wissen","0","⌫"]]
        for r, row in enumerate(labels):
            for c, lab in enumerate(row):
                tk.Button(grid, text=lab, font=btn_font, width=btn_w, height=btn_h,
                          command=lambda x=lab: self._keypad_press(x))\
                    .grid(row=r, column=c, **pad)

        tk.Button(self.keypad_win, text="ONTGRENDEL",
                  font=("Segoe UI", 18, "bold"), bg="#3A6FF2", fg="white",
                  command=self._keypad_try_unlock)\
            .pack(fill="x", padx=16, pady=(8, 10))

        # toetsenbord
        self.keypad_win.bind("<Key>", self._kb_type)
        self.keypad_win.bind("<BackSpace>", self._kb_backspace)
        self.keypad_win.bind("<Escape>", self._kb_clear)
        self.keypad_win.bind("<Return>", lambda e: self._keypad_try_unlock())
        self.keypad_win.focus_set()

    def _on_keypad_close(self):
        self.entered = ""
        if self.mask_var is not None:
            self.mask_var.set("")
        if self.keypad_win and self.keypad_win.winfo_exists():
            self.keypad_win.withdraw()
        try: self.canvas.focus_set()
        except Exception: pass

    # keypad invoer
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
            self._on_keypad_close()
            self._start_relock_timer()   # altijd relock starten
        else:
            self.mask_var.set("Foutieve code")
            self.keypad_win.after(900, lambda: self.mask_var.set(""))
            self.entered = ""

    # ----- Serieel (ESP32 / adapter) -----
    def on_serial_trigger(self):
        now = time.time()
        if now - self.last_trigger < TRIGGER_MIN_INTERVAL:
            return
        self.last_trigger = now
        self.hide_overlay()
        self._start_relock_timer()         # altijd relock starten

    def _serial_loop(self):
        if not HAS_SERIAL:
            return
        ser = None
        while True:
            try:
                if ser is None or not ser.is_open:
                    try:
                        ser = serial.Serial(COM_PORT, BAUDRATE, timeout=0.2)
                    except Exception:
                        time.sleep(1.0); continue
                # lees regels en bytes en reageer alleen op het commando 'TRIGGER'
                raw = ser.readline()
                try:
                    data = raw.decode(errors="ignore").strip()
                except AttributeError:
                    # als pyserial al str teruggeeft
                    data = (raw or "").strip()
                if data == "TRIGGER":
                    self.root.after(0, self.on_serial_trigger); time.sleep(0.1)
                else:
                    raw = ser.read(16)
                    try:
                        bdata = raw.decode(errors="ignore").strip()
                    except AttributeError:
                        bdata = (raw or "").strip()
                    if bdata == "TRIGGER":
                        self.root.after(0, self.on_serial_trigger); time.sleep(0.1)
            except Exception:
                try:
                    if ser: ser.close()
                except Exception: pass
                ser = None
                time.sleep(1.0)

def main():
    root = tk.Tk()
    SacoaOverlayApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()