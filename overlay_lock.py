# overlay_lock.py  (v1.2 – compact keypad + brede ONTGRENDEL-balk + lock-button keep-alive)
# - Bediening op gekozen monitor met "🔒 Lock nu" rechts-onder, altijd zichtbaar
# - Fullscreen overlay met numeriek keypad
# - Geen auto-relock; handmatig lock/unlock

import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import sys

# ===== Instellingen =====
PIN = "1423"                 # Toegangscode
SCREEN_INDEX = 0             # 0 = primair, 1 = tweede, 2 = derde, ...
BG_COLOR = "#111122"         # Achtergrond overlay

# Keypad-knoppen (compacter dan voorheen)
KEY_BTN_FONT = ("Segoe UI", 24)
KEY_BTN_W = 6                # breedte in tk "chars"
KEY_BTN_H = 2                # hoogte in tk "rows"
KEY_PADX = 6
KEY_PADY = 6

# Ontgrendel-balk (extra opvallend)
UNLOCK_TEXT = "ONTGRENDEL"
UNLOCK_FONT = ("Segoe UI", 28, "bold")
UNLOCK_BG = "#3A6FF2"
UNLOCK_FG = "white"
UNLOCK_ACTIVE_BG = "#2E55B8"
UNLOCK_BTN_W = 32            # extra breed
UNLOCK_BTN_H = 4             # extra hoog

# "Lock nu" knop (rechtsonder, keep-alive)
LOCKBTN_W, LOCKBTN_H = 120, 36
LOCKBTN_MARGIN = 20
KEEP_ALIVE_MS = 1000         # elke 1s bovenaan houden

# ===== Win32 monitor info =====
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

# ===== App =====
class DisplayLockApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        screens = get_monitors()
        if not screens:
            messagebox.showerror("DisplayLock", "Geen schermen gevonden.")
            sys.exit(1)

        self.screen_idx = SCREEN_INDEX if 0 <= SCREEN_INDEX < len(screens) else 0
        self.sx, self.sy, self.sr, self.sb = screens[self.screen_idx]
        self.swidth = self.sr - self.sx
        self.sheight = self.sb - self.sy

        self.lock_btn_win = None
        self.overlay = None
        self.entered = ""

        self._build_overlay()
        self._build_lock_button()
        self._keep_alive()  # knop altijd zichtbaar houden

    # -------- Lock-knop ----------
    def _build_lock_button(self):
        if self.lock_btn_win and self.lock_btn_win.winfo_exists():
            self._place_lock_button()
            self.lock_btn_win.deiconify()
            self.lock_btn_win.lift()
            self.lock_btn_win.attributes("-topmost", True)
            return

        self.lock_btn_win = tk.Toplevel(self.root)
        self.lock_btn_win.overrideredirect(True)
        self.lock_btn_win.attributes("-topmost", True)
        self.lock_btn_win.configure(bg="#F2F2F7")
        self.lock_btn_win.bind("<Unmap>", lambda e: self.lock_btn_win.after(50, self._show_lock_button))
        self.lock_btn_win.bind("<Map>",   lambda e: self._place_lock_button())

        btn = tk.Button(
            self.lock_btn_win, text="🔒 Lock nu", font=("Segoe UI", 10),
            width=14, height=1, command=self.lock_now,
            relief="flat", bg="#F2F2F7", activebackground="#E6E6EC"
        )
        btn.pack()
        self._place_lock_button()

    def _place_lock_button(self):
        x = self.sx + self.swidth  - LOCKBTN_W - LOCKBTN_MARGIN
        y = self.sy + self.sheight - LOCKBTN_H - LOCKBTN_MARGIN
        self.lock_btn_win.geometry(f"{LOCKBTN_W}x{LOCKBTN_H}+{x}+{y}")

    def _show_lock_button(self):
        try:
            if not (self.lock_btn_win and self.lock_btn_win.winfo_exists()):
                self._build_lock_button()
            else:
                self.lock_btn_win.deiconify()
                self._place_lock_button()
                self.lock_btn_win.lift()
                self.lock_btn_win.attributes("-topmost", True)
        except tk.TclError:
            self._build_lock_button()

    def _keep_alive(self):
        self._show_lock_button()
        self.root.after(KEEP_ALIVE_MS, self._keep_alive)

    # -------- Overlay ----------
    def _build_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg=BG_COLOR)
        self.overlay.geometry(f"{self.swidth}x{self.sheight}+{self.sx}+{self.sy}")

        title = tk.Label(self.overlay, text="TOEGANGSCODE VEREIST",
                         fg="white", bg=BG_COLOR, font=("Segoe UI", 34, "bold"))
        title.pack(pady=(24, 8))

        subtitle = tk.Label(self.overlay, text="Vraag een medewerker om te ontgrendelen.",
                            fg="#DDDDFF", bg=BG_COLOR, font=("Segoe UI", 18))
        subtitle.pack(pady=(0, 12))

        # Masked display
        self.mask_var = tk.StringVar(value="")
        display = tk.Label(
            self.overlay, textvariable=self.mask_var, fg="white", bg="#22223A",
            font=("Segoe UI", 32), width=26, height=1, padx=16, pady=10
        )
        display.pack(pady=(0, 24))

        # Keypad
        labels = [
            ["1","2","3"],
            ["4","5","6"],
            ["7","8","9"],
            ["Wissen","0","⌫"]
        ]
        for row in labels:
            fr = tk.Frame(self.overlay, bg=BG_COLOR); fr.pack()
            for lab in row:
                b = tk.Button(
                    fr, text=lab, font=KEY_BTN_FONT,
                    width=KEY_BTN_W, height=KEY_BTN_H,
                    command=lambda x=lab: self.on_key(x)
                )
                b.pack(side="left", padx=KEY_PADX, pady=KEY_PADY)

        # ONTGRENDEL – brede/hoge balk
        unlock = tk.Button(
            self.overlay, text=UNLOCK_TEXT, font=UNLOCK_FONT,
            width=UNLOCK_BTN_W, height=UNLOCK_BTN_H,
            bg=UNLOCK_BG, fg=UNLOCK_FG, activebackground=UNLOCK_ACTIVE_BG,
            command=self.try_unlock
        )
        unlock.pack(pady=(20, 32))

    # -------- Logica ----------
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
            self._show_lock_button()
        else:
            self.mask_var.set("Foutieve code")
            self.overlay.after(900, lambda: self.mask_var.set(""))
            self.entered = ""

def main():
    root = tk.Tk()
    app = DisplayLockApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
