# overlay_lock.py
# - "🔒 Lock nu" knop rechtsonder op gekozen (bedienings)scherm
# - Fullscreen overlay met numeriek touch-keypad
# - Geen auto-relock, alleen handmatig lock/unlock

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes

# ===== Instellingen =====
PIN = "2580"          # Toegangscode
SCREEN_INDEX = 0      # 0 = primair, 1 = tweede, 2 = derde scherm...
BTN_SIZE = (160, 110) # keypad knopgrootte
GAP = 16              # ruimte tussen knoppen
BG_COLOR = "#111122"  # overlay achtergrondkleur

# ===== Win32 monitor info via ctypes =====
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(wintypes.RECT), ctypes.c_double)
monitors = []
def _monitor_enum(hMonitor, hdcMonitor, lprcMonitor, dwData):
    r = lprcMonitor.contents
    monitors.append((r.left, r.top, r.right, r.bottom))
    return 1

def get_monitors():
    monitors.clear()
    user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_monitor_enum), 0)
    return monitors[:]

# ===== App =====
class DisplayLockApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        screens = get_monitors()
        if not screens:
            messagebox.showerror("DisplayLock", "Geen schermen gevonden.")
            raise SystemExit

        if SCREEN_INDEX < 0 or SCREEN_INDEX >= len(screens):
            messagebox.showwarning("DisplayLock", f"SCREEN_INDEX {SCREEN_INDEX} ongeldig. Gebruik 0..{len(screens)-1}. Valt terug op 0 (primair).")
            self.screen_idx = 0
        else:
            self.screen_idx = SCREEN_INDEX

        self.sx, self.sy, self.sr, self.sb = screens[self.screen_idx]
        self.swidth = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self._build_overlay()
        self._build_lock_button()

    # ===== Lock knop rechtsonder =====
    def _build_lock_button(self):
        self.lock_btn_win = tk.Toplevel(self.root)
        self.lock_btn_win.overrideredirect(True)
        self.lock_btn_win.attributes("-topmost", True)
        self.lock_btn_win.configure(bg="#F2F2F7")

        btn = tk.Button(self.lock_btn_win, text="🔒 Lock nu", font=("Segoe UI", 10),
                        width=14, height=1, command=self.lock_now, relief="flat", bg="#F2F2F7")
        btn.pack()

        margin = 20
        btn_w, btn_h = 120, 36
        x = self.sx + self.swidth - btn_w - margin
        y = self.sy + self.sheight - btn_h - margin
        self.lock_btn_win.geometry(f"{btn_w}x{btn_h}+{x}+{y}")

    # ===== Overlay (fullscreen) =====
    def _build_overlay(self):
        self.entered = ""
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg=BG_COLOR)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        # Titel
        title = tk.Label(self.overlay, text="TOEGANGSCODE VEREIST", fg="white",
                         bg=BG_COLOR, font=("Segoe UI", 34, "bold"))
        title.pack(pady=(24, 8))

        subtitle = tk.Label(self.overlay, text="Vraag een medewerker om te ontgrendelen.",
                            fg="#DDDDFF", bg=BG_COLOR, font=("Segoe UI", 18))
        subtitle.pack(pady=(0, 12))

        # Masked display
        self.mask_var = tk.StringVar(value="")
        display = tk.Label(self.overlay, textvariable=self.mask_var, fg="white", bg="#22223A",
                           font=("Segoe UI", 32), width=26, height=1, padx=16, pady=10)
        display.pack(pady=(0, 24))

        # Keypad
        labels = [
            ["1","2","3"],
            ["4","5","6"],
            ["7","8","9"],
            ["Wissen","0","⌫"]
        ]

        for row in labels:
            row_frame = tk.Frame(self.overlay, bg=BG_COLOR)
            row_frame.pack()
            for lab in row:
                b = tk.Button(row_frame, text=lab, font=("Segoe UI", 26), width=8, height=3,
                              command=lambda x=lab: self.on_key(x))
                b.pack(side="left", padx=8, pady=8)

        # Ontgrendel knop
        unlock = tk.Button(self.overlay, text="Ontgrendel", font=("Segoe UI", 28),
                           width=26, height=2, command=self.try_unlock)
        unlock.pack(pady=(16, 24))

    # ===== Keypad logica =====
    def on_key(self, label):
        if label == "Wissen":
            self.entered = ""
        elif label == "⌫":
            self.entered = self.entered[:-1]
        else:
            if len(self.entered) < 8:
                self.entered += label
            else:
                self.overlay.bell()
        self._update_mask()

    def _update_mask(self):
        self.mask_var.set("•" * len(self.entered) if self.entered else "")

    def lock_now(self):
        self.entered = ""
        self._update_mask()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)

    def try_unlock(self):
        if self.entered == PIN:
            self.entered = ""
            self._update_mask()
            self.overlay.withdraw()
        else:
            self.mask_var.set("Foutieve code")
            self.overlay.after(800, lambda: self.mask_var.set(""))
            self.entered = ""

def main():
    root = tk.Tk()
    app = DisplayLockApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()