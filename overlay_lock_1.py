# overlay_lock_nfc.py  (v1.4 + NFC support)
# Zelfde UI-setup als jouw versie; toegevoegd: NFC via pyscard (PC/SC)
import tkinter as tk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import sys
from pathlib import Path
import threading
import time

# --- NFC (pyscard) imports (optioneel, installeer met `pip install pyscard`) ---
try:
    from smartcard.System import readers
    from smartcard.Exceptions import NoReadersException, CardConnectionException
    HAVE_PYSCARD = True
except Exception:
    HAVE_PYSCARD = False

# ===== Instellingen UI =====
SCREEN_INDEX = 0             # 0 = primair, 1 = tweede, 2 = derde, ...
BG_COLOR = "#111122"

KEY_BTN_FONT = ("Segoe UI", 24)
KEY_BTN_W = 6
KEY_BTN_H = 2
KEY_PADX = 6
KEY_PADY = 6

UNLOCK_TEXT = "ONTGRENDEL"
UNLOCK_FONT = ("Segoe UI", 28, "bold")
UNLOCK_BG = "#3A6FF2"
UNLOCK_FG = "white"
UNLOCK_ACTIVE_BG = "#2E55B8"
UNLOCK_BTN_W = 32
UNLOCK_BTN_H = 4

# Lock-knop instellingen (groter + meer marge)
LOCKBTN_W, LOCKBTN_H = 150, 45
LOCKBTN_MARGIN = 40
KEEP_ALIVE_MS = 1000

# Toetsenbord: maximale codelengte (alfanumeriek)
MAX_CODE_LEN = 32

# ===== PIN-bestand =====
PINS_FILENAME = "overlay_lock_pins.txt"   # ligt in dezelfde map als dit script

# ===== NFC instellingen =====
AUTO_UNLOCK_ON_NFC = True   # True = probeer direct te ontgrendelen als NFC gelezen wordt
NFC_POLL_INTERVAL = 0.8     # seconden tussen polls (lage belasting)

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

# ===== PIN loader =====
def ensure_pins_file(path: Path):
    if path.exists():
        return
    sample = (
        "# overlay_lock_pins.txt — één code per regel\n"
        "# Optioneel: PIN: Naam\n"
        "2580: Medewerker\n"
        "8246\n"
    )
    path.write_text(sample, encoding="utf-8")

def load_pins(path: Path):
    """
    Leest codes uit bestand.
    - Lege regels en regels die met # beginnen worden genegeerd.
    - 'PIN: Naam' wordt ondersteund (naam niet verplicht).
    Retourneert (set_pins, dict_pin_to_name).
    """
    pins = set()
    names = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                pin, name = line.split(":", 1)
                pin = pin.strip()
                name = name.strip()
                if pin:
                    # normalize: store uppercase hex and raw
                    pins.add(pin)
                    if name:
                        names[pin] = name
            else:
                pins.add(line)
    except FileNotFoundError:
        pass
    return pins, names

# ===== App =====
class DisplayLockApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        # pad naar pins-bestand
        self.base_dir = Path(__file__).resolve().parent
        self.pins_path = self.base_dir / PINS_FILENAME
        ensure_pins_file(self.pins_path)
        self.pins, self.pin_names = load_pins(self.pins_path)
        self.pins_mtime = self._pins_mtime()

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

        # NFC thread control
        self.nfc_thread = None
        self.nfc_stop = threading.Event()

        self._build_overlay()
        self._build_lock_button()
        self._keep_alive()   # lock-knop bovenaan houden

        # start NFC achtergrondthread (indien beschikbaar)
        if HAVE_PYSCARD:
            self._start_nfc_thread()
        else:
            print("pyscard niet gevonden; NFC ondersteuning uitgeschakeld. (pip install pyscard)")

        # Zorg dat we netjes stoppen bij sluiten
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

    # --- helpers pins ---
    def _pins_mtime(self):
        try:
            return self.pins_path.stat().st_mtime
        except FileNotFoundError:
            return 0

    def _reload_pins_if_changed(self):
        mtime = self._pins_mtime()
        if mtime != self.pins_mtime:
            self.pins, self.pin_names = load_pins(self.pins_path)
            self.pins_mtime = mtime

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
            self.lock_btn_win, text="🔒 Lock nu", font=("Segoe UI", 11, "bold"),
            width=16, height=2, command=self.lock_now,
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

        self.mask_var = tk.StringVar(value="")
        display = tk.Label(
            self.overlay, textvariable=self.mask_var, fg="white", bg="#22223A",
            font=("Segoe UI", 32), width=26, height=1, padx=16, pady=10
        )
        display.pack(pady=(0, 24))

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

        unlock = tk.Button(
            self.overlay, text=UNLOCK_TEXT, font=UNLOCK_FONT,
            width=UNLOCK_BTN_W, height=UNLOCK_BTN_H,
            bg=UNLOCK_BG, fg=UNLOCK_FG, activebackground=UNLOCK_ACTIVE_BG,
            command=self.try_unlock
        )
        unlock.pack(pady=(20, 32))

        # --- Keyboard support ---
        self.overlay.bind("<Key>", self.on_keypress)         # alfanumeriek toevoegen
        self.overlay.bind("<BackSpace>", self.on_backspace)  # backspace
        self.overlay.bind("<Escape>", self.on_clear)         # esc = wissen
        self.overlay.bind("<Return>", lambda e: self.try_unlock())  # enter = ontgrendelen

    # -------- Logica ----------
    def on_key(self, label):
        if label == "Wissen":
            self.entered = ""
        elif label == "⌫":
            self.entered = self.entered[:-1]
        else:
            if len(self.entered) < MAX_CODE_LEN:
                self.entered += label
            else:
                self.overlay.bell()
        self._update_mask()

    def on_keypress(self, event):
        ch = event.char
        if ch and ch.isalnum():  # alleen letters/cijfers
            if len(self.entered) < MAX_CODE_LEN:
                self.entered += ch
                self._update_mask()
            else:
                self.overlay.bell()

    def on_backspace(self, event):
        if self.entered:
            self.entered = self.entered[:-1]
            self._update_mask()

    def on_clear(self, event):
        self.entered = ""
        self._update_mask()

    def _update_mask(self):
        # toon • tekens of foutmelding
        self.mask_var.set("•" * len(self.entered) if self.entered else "")

    def lock_now(self):
        self.entered = ""
        self._update_mask()
        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)
        self.overlay.focus_set()  # direct kunnen typen met toetsenbord

    def try_unlock(self):
        # Herlaad codes wanneer bestand is gewijzigd (hot-reload)
        self._reload_pins_if_changed()

        # Probeer exact match (vergelijk raw en uppercase hex)
        e = self.entered.strip()
        # normalize: probeer uppercase hex ook
        if e in self.pins or e.upper() in self.pins:
            self.entered = ""
            self._update_mask()
            self.overlay.withdraw()
            self._show_lock_button()
        else:
            self.mask_var.set("Foutieve code")
            self.overlay.after(900, lambda: self.mask_var.set(""))
            self.entered = ""

    # -------- NFC integratie ----------
    def _start_nfc_thread(self):
        if self.nfc_thread and self.nfc_thread.is_alive():
            return
        self.nfc_stop.clear()
        self.nfc_thread = threading.Thread(target=self._nfc_worker, daemon=True)
        self.nfc_thread.start()

    def _nfc_worker(self):
        """
        Pollt beschikbaarheid van readers en probeert UID uit te lezen met APDU FF CA 00 00 00.
        Wanneer een UID wordt gelezen, convert naar HEX zonder spaties en post naar UI-thread.
        """
        last_reader = None
        while not self.nfc_stop.is_set():
            try:
                rlist = readers()
                if not rlist:
                    # geen readers gevonden, wacht en retry
                    time.sleep(1.0)
                    continue

                # kies eerste reader (je kunt hier uitbreiden voor meerdere)
                rdr = rlist[0]
                if last_reader != str(rdr):
                    print(f"NFC reader: {rdr}")
                    last_reader = str(rdr)

                try:
                    connection = rdr.createConnection()
                    # connect met default protocol (kan exception opleveren als geen kaart)
                    try:
                        connection.connect()
                    except Exception:
                        # geen kaart aanwezig; wacht kort en poll opnieuw
                        time.sleep(NFC_POLL_INTERVAL)
                        continue

                    # APDU om UID te krijgen (veel gebruikt door PC/SC readers):
                    GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                    try:
                        response, sw1, sw2 = connection.transmit(GET_UID_APDU)
                    except CardConnectionException:
                        response = []
                        sw1 = sw2 = None

                    if response:
                        # response is list of ints: converteer naar hex string zonder spaties, uppercase
                        uid_hex = "".join(f"{b:02X}" for b in response)
                        # post naar main-thread
                        self.root.after(0, lambda uid=uid_hex: self._on_nfc_read(uid))
                        # kleine pauze om dubbel-lezen te voorkomen
                        time.sleep(1.0)
                    else:
                        time.sleep(NFC_POLL_INTERVAL)
                except Exception:
                    # soms kan createConnection/connect falen; log en continue
                    time.sleep(NFC_POLL_INTERVAL)
            except NoReadersException:
                time.sleep(1.0)
            except Exception:
                # defensieve catch-all; log en blijf proberen
                time.sleep(1.0)

    def _on_nfc_read(self, uid_hex: str):
        """
        UI-thread: handel gelezen UID (HEX) af.
        Hier zetten we de ingevoerde code naar de UID (optioneel: direct ontgrendelen).
        """
        # Toon kort de HEX in het invoerveld (normaal masked), we tonen plain voor korte tijd
        self.entered = uid_hex
        self.mask_var.set(uid_hex)  # tijdelijk zichtbaar
        # probeer hot-reload van pins ook
        self._reload_pins_if_changed()

        if AUTO_UNLOCK_ON_NFC:
            # als match -> ontgrendelen, anders geef feedback
            if uid_hex in self.pins or uid_hex.upper() in self.pins:
                # valide kaart
                self.try_unlock()
                return
            else:
                # toon foutmelding kort en reset
                self.overlay.after(900, lambda: self.mask_var.set(""))
                self.entered = ""
        else:
            # laat de HEX even zichtbaar en daarna vervangen door mask
            def hide_after():
                self._update_mask()
            self.overlay.after(1200, hide_after)

    def shutdown(self):
        # stop NFC thread netjes
        self.nfc_stop.set()
        if self.nfc_thread and self.nfc_thread.is_alive():
            # thread is daemon, maar probeer toch kort te wachten
            self.nfc_thread.join(timeout=0.5)
        try:
            self.root.destroy()
        except Exception:
            pass

def main():
    root = tk.Tk()
    app = DisplayLockApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()