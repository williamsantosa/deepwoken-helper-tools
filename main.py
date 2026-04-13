import tkinter as tk
import pyautogui
import pygetwindow as gw
import keyboard
import threading
import time
import json
import os
import numpy as np
import mss
import easyocr
from rapidfuzz import process, fuzz
from PIL import Image, ImageTk

# ── Hardcoded constants ─────────────────────────────────────────────────
PREFIX = "ctrl+"
CATCHPHRASES = [
    "Me-wow, is that the latest Felinor fashion?",
    "So, what's keeping you busy these days?",
    "Hey hivekin, can I bug you for a moment?",
    "So, how's work?",
    "Wow, this breeze is great, right?",
    "Sometimes I have really deep thoughts about life and stuff.",
    "Some weather we're having, huh?",
    "You ever been to a Canor restaurant? The food's pretty howlright."
]

# ── Default config values (overridden by config.json if present) ───────
DEFAULTS = {
    "auto_hotkey": "F1",
    "full_auto_hotkey": "F2",
    "loop_hotkey": "F3",
    "input_click_x": 0.50,
    "input_click_y": 0.87,
    "ocr_left": 0.15,
    "ocr_top": 0.25,
    "ocr_right": 0.85,
    "ocr_bottom": 0.55,
    "match_threshold": 60,
    "window_title": "Roblox",
    "dialog_open_delay": 1.0,
    "submit_delay": 0.3,
    "loop_interval": 1.0,
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# ── Globals ─────────────────────────────────────────────────────────────
config: dict = {}
ocr_reader = None
gui_app = None
loop_running = False


def load_config():
    global config
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass


def save_config():
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_ocr_reader():
    """Lazy-init the EasyOCR reader so startup isn't blocked by model loading."""
    global ocr_reader
    if ocr_reader is None:
        ocr_reader = easyocr.Reader(["en"], gpu=False)
    return ocr_reader


def find_roblox_window():
    """Return the first Roblox window, or None."""
    windows = gw.getWindowsWithTitle(config["window_title"])
    if not windows:
        return None
    return windows[0]


def capture_region(win, region_pct):
    """Capture a sub-region of a window defined by relative percentages.

    region_pct: (left%, top%, right%, bottom%) each in [0, 1]
    Returns a numpy BGR image array.
    """
    left_pct, top_pct, right_pct, bottom_pct = region_pct
    x = win.left + int(win.width * left_pct)
    y = win.top + int(win.height * top_pct)
    w = int(win.width * (right_pct - left_pct))
    h = int(win.height * (bottom_pct - top_pct))

    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": w, "height": h}
        img = np.array(sct.grab(monitor))
    # mss returns BGRA; drop alpha channel for EasyOCR
    return img[:, :, :3]


def detect_catchphrase(win):
    """Screenshot the speech-bubble region, OCR it, and fuzzy-match to a known catchphrase.

    Returns (matched_phrase, score) or (None, 0) if no good match.
    """
    ocr_region = (config["ocr_left"], config["ocr_top"],
                   config["ocr_right"], config["ocr_bottom"])
    img = capture_region(win, ocr_region)
    reader = get_ocr_reader()
    results = reader.readtext(img, detail=0)
    ocr_text = " ".join(results)
    if not ocr_text.strip():
        return None, 0

    best = process.extractOne(ocr_text, CATCHPHRASES, scorer=fuzz.token_set_ratio)
    if best is None:
        return None, 0
    phrase, score, _idx = best
    if score >= config["match_threshold"]:
        return phrase, score
    return None, score


def focus_roblox(win):
    """Bring the Roblox window to the foreground."""
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:
        # pygetwindow.activate() can throw on some setups; fall back to a click
        pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)
    time.sleep(0.15)


def click_input_box(win):
    """Click the text input box and wait for it to gain focus."""
    click_x = win.left + int(win.width * config["input_click_x"])
    click_y = win.top + int(win.height * config["input_click_y"])
    pyautogui.click(click_x, click_y)
    time.sleep(0.15)
    # Second click to be sure — Roblox sometimes needs it
    pyautogui.click(click_x, click_y)
    time.sleep(0.3)


def auto_smalltalk():
    """Full automated loop: find window -> OCR -> click input -> type -> submit."""
    update_status("Searching for Roblox window...")

    win = find_roblox_window()
    if win is None:
        update_status("ERROR: Roblox window not found")
        return

    focus_roblox(win)

    update_status("Running OCR on speech bubble...")
    phrase, score = detect_catchphrase(win)
    if phrase is None:
        update_status(f"No match found (best score: {score:.0f})")
        return

    update_status(f"Matched: \"{phrase}\" (score: {score:.0f}) — typing...")

    click_input_box(win)
    keyboard.write(phrase, delay=0.01)
    time.sleep(0.1)
    keyboard.press_and_release("enter")

    update_status(f"Done! Typed: \"{phrase}\"")


def full_auto_smalltalk():
    """Fully automated: left-click NPC to open dialog, wait, OCR, type, submit."""
    update_status("Full-auto: clicking to open dialog...")

    win = find_roblox_window()
    if win is None:
        update_status("ERROR: Roblox window not found")
        return

    focus_roblox(win)

    # Left-click the center of the window to open the NPC dialog
    center_x = win.left + win.width // 2
    center_y = win.top + win.height // 2
    pyautogui.click(center_x, center_y)

    time.sleep(config["dialog_open_delay"])

    update_status("Full-auto: running OCR...")
    phrase, score = detect_catchphrase(win)
    if phrase is None:
        update_status(f"No match found (best score: {score:.0f})")
        return

    update_status(f"Matched: \"{phrase}\" (score: {score:.0f}) — typing...")

    click_input_box(win)
    keyboard.write(phrase, delay=0.01)
    time.sleep(config["submit_delay"])
    keyboard.press_and_release("enter")

    update_status(f"Full-auto done! Typed: \"{phrase}\"")


def toggle_loop():
    """Toggle the full-auto loop on/off."""
    global loop_running
    if loop_running:
        loop_running = False
        update_status("Loop stopped")
    else:
        loop_running = True
        update_status("Loop started — press again to stop")
        threading.Thread(target=_loop_worker, daemon=True).start()


def _loop_worker():
    """Repeatedly runs full_auto_smalltalk until loop_running is cleared."""
    global loop_running
    while loop_running:
        win = find_roblox_window()
        if win is None:
            update_status("Loop: Roblox window not found, retrying...")
            time.sleep(config["loop_interval"])
            continue

        focus_roblox(win)

        center_x = win.left + win.width // 2
        center_y = win.top + win.height // 2
        pyautogui.click(center_x, center_y)

        time.sleep(config["dialog_open_delay"])

        if not loop_running:
            break

        phrase, score = detect_catchphrase(win)
        if phrase is None:
            update_status(f"Loop: no match (score: {score:.0f}), retrying...")
            time.sleep(config["loop_interval"])
            continue

        update_status(f"Loop: typing \"{phrase}\" (score: {score:.0f})")

        click_input_box(win)
        keyboard.write(phrase, delay=0.01)
        time.sleep(config["submit_delay"])
        keyboard.press_and_release("enter")

        time.sleep(config["loop_interval"])

    loop_running = False
    update_status("Loop stopped")


def update_status(msg):
    """Thread-safe status update for the GUI."""
    if gui_app is not None:
        gui_app.after(0, gui_app.set_status, msg)
    print(msg)


def type_catchphrase(index):
    time.sleep(0.5)
    keyboard.write(CATCHPHRASES[index], delay=0.01)


def setup_hotkeys():
    for i in range(len(CATCHPHRASES)):
        keyboard.add_hotkey(f"{PREFIX}{i+1}", type_catchphrase, args=[i])
    keyboard.add_hotkey(config["auto_hotkey"],
                        lambda: threading.Thread(target=auto_smalltalk, daemon=True).start())
    keyboard.add_hotkey(config["full_auto_hotkey"],
                        lambda: threading.Thread(target=full_auto_smalltalk, daemon=True).start())
    keyboard.add_hotkey(config["loop_hotkey"], toggle_loop)


def capture_full_window(win):
    """Screenshot the entire Roblox window, return a PIL Image."""
    with mss.mss() as sct:
        monitor = {"left": win.left, "top": win.top,
                   "width": win.width, "height": win.height}
        raw = sct.grab(monitor)
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


class ScreenPicker(tk.Toplevel):
    """Overlay showing a Roblox screenshot for visual coordinate picking.

    mode="click"  – single click returns (rel_x, rel_y)
    mode="drag"   – click-and-drag returns (left%, top%, right%, bottom%)
    """

    MAX_DISPLAY = 900  # max width/height for the preview

    def __init__(self, parent, pil_img, win_size, mode="click", callback=None,
                 current_click=None, current_region=None):
        super().__init__(parent)
        self.mode = mode
        self.callback = callback
        self.win_w, self.win_h = win_size

        self.scale = min(self.MAX_DISPLAY / self.win_w,
                         self.MAX_DISPLAY / self.win_h, 1.0)
        disp_w = int(self.win_w * self.scale)
        disp_h = int(self.win_h * self.scale)

        resized = pil_img.resize((disp_w, disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(resized)

        self.title("Click to pick" if mode == "click" else "Drag to select region")
        self.geometry(f"{disp_w}x{disp_h + 30}")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(bg="#2b2b2b")

        hint_text = ("Click where the text input box is"
                     if mode == "click"
                     else "Click and drag over the speech bubble area")
        hint = tk.Label(self, text=hint_text, font=("Arial", 10),
                        bg="#2b2b2b", fg="#aaaaaa")
        hint.pack(side="top", pady=(4, 0))

        self.canvas = tk.Canvas(self, width=disp_w, height=disp_h,
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side="top")
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

        if mode == "click" and current_click:
            cx = int(current_click[0] * disp_w)
            cy = int(current_click[1] * disp_h)
            self._draw_crosshair(cx, cy)

        if mode == "drag" and current_region:
            l, t, r, b = current_region
            self.canvas.create_rectangle(
                int(l * disp_w), int(t * disp_h),
                int(r * disp_w), int(b * disp_h),
                outline="#00ff00", width=2, dash=(4, 4), tags="existing")

        self._drag_rect = None
        self._start_x = 0
        self._start_y = 0

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        if mode == "drag":
            self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.transient(parent)
        self.grab_set()

    def _draw_crosshair(self, cx, cy, tag="crosshair"):
        w = self.canvas.winfo_reqwidth()
        h = self.canvas.winfo_reqheight()
        self.canvas.create_line(cx, 0, cx, h, fill="#ff4444", width=1,
                                dash=(3, 3), tags=tag)
        self.canvas.create_line(0, cy, w, cy, fill="#ff4444", width=1,
                                dash=(3, 3), tags=tag)
        r = 6
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline="#ff4444", width=2, tags=tag)

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        if self.mode == "click":
            self.canvas.delete("crosshair")
            self._draw_crosshair(event.x, event.y)

    def _on_motion(self, event):
        if self._drag_rect:
            self.canvas.delete(self._drag_rect)
        self._drag_rect = self.canvas.create_rectangle(
            self._start_x, self._start_y, event.x, event.y,
            outline="#00ff00", width=2, dash=(4, 4))

    def _on_release(self, event):
        disp_w = self.canvas.winfo_reqwidth()
        disp_h = self.canvas.winfo_reqheight()

        if self.mode == "click":
            rx = round(event.x / disp_w, 4)
            ry = round(event.y / disp_h, 4)
            rx = max(0.0, min(1.0, rx))
            ry = max(0.0, min(1.0, ry))
            if self.callback:
                self.callback((rx, ry))
            self.destroy()

        elif self.mode == "drag":
            x1 = max(0, min(self._start_x, event.x))
            y1 = max(0, min(self._start_y, event.y))
            x2 = min(disp_w, max(self._start_x, event.x))
            y2 = min(disp_h, max(self._start_y, event.y))
            if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
                return  # too small, ignore
            rl = round(x1 / disp_w, 4)
            rt = round(y1 / disp_h, 4)
            rr = round(x2 / disp_w, 4)
            rb = round(y2 / disp_h, 4)
            if self.callback:
                self.callback((rl, rt, rr, rb))
            self.destroy()


class SettingsDialog(tk.Toplevel):
    """Modal dialog for editing runtime configuration."""

    TEXT_FIELDS = [
        ("auto_hotkey",       "Auto Hotkey (OCR only)",     str),
        ("full_auto_hotkey",  "Full-Auto Hotkey",           str),
        ("loop_hotkey",       "Loop Hotkey (start/stop)",   str),
        ("window_title",      "Roblox Window Title",        str),
        ("match_threshold",   "Match Threshold (0-100)",    int),
        ("dialog_open_delay", "Dialog Open Delay (sec)",    float),
        ("submit_delay",      "Submit Delay (sec)",         float),
        ("loop_interval",     "Loop Interval (sec)",        float),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg="#2b2b2b")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(parent)
        self.grab_set()

        self.entries: dict[str, tk.Entry] = {}
        self._click_pos: tuple[float, float] = (
            config["input_click_x"], config["input_click_y"])
        self._ocr_region: tuple[float, float, float, float] = (
            config["ocr_left"], config["ocr_top"],
            config["ocr_right"], config["ocr_bottom"])
        self._build_ui()
        self.geometry("")

    def _build_ui(self):
        BG = "#2b2b2b"
        FG = "#d4d4d4"
        ENTRY_BG = "#1e1e1e"

        pad_frame = tk.Frame(self, bg=BG)
        pad_frame.pack(padx=16, pady=12, fill="both", expand=True)

        row = 0
        for key, label, _ in self.TEXT_FIELDS:
            lbl = tk.Label(pad_frame, text=label, font=("Arial", 10),
                           bg=BG, fg=FG, anchor="w")
            lbl.grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))

            entry = tk.Entry(pad_frame, width=20, font=("Consolas", 10),
                             bg=ENTRY_BG, fg=FG, insertbackground=FG,
                             borderwidth=1, relief="solid")
            entry.insert(0, str(config[key]))
            entry.grid(row=row, column=1, columnspan=2, sticky="e", pady=3)
            self.entries[key] = entry
            row += 1

        # ── Separator ──
        sep = tk.Frame(pad_frame, height=1, bg="#555555")
        sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        row += 1

        # ── Input click position (visual picker) ──
        lbl = tk.Label(pad_frame, text="Input Click Position", font=("Arial", 10),
                       bg=BG, fg=FG, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))

        self._click_label_var = tk.StringVar(
            value=f"({self._click_pos[0]:.2f}, {self._click_pos[1]:.2f})")
        click_val = tk.Label(pad_frame, textvariable=self._click_label_var,
                             font=("Consolas", 10), bg=BG, fg="#7ec87e",
                             anchor="w", width=14)
        click_val.grid(row=row, column=1, sticky="w", pady=3)

        pick_btn = tk.Button(
            pad_frame, text="Pick", width=6, font=("Arial", 9),
            bg="#3a5e8a", fg="#ffffff", activebackground="#4a7eba",
            relief="flat", command=self._pick_click_pos,
        )
        pick_btn.grid(row=row, column=2, sticky="e", pady=3, padx=(4, 0))
        row += 1

        # ── OCR region (visual picker) ──
        lbl2 = tk.Label(pad_frame, text="OCR Scan Region", font=("Arial", 10),
                        bg=BG, fg=FG, anchor="w")
        lbl2.grid(row=row, column=0, sticky="w", pady=3, padx=(0, 12))

        self._region_label_var = tk.StringVar()
        self._refresh_region_label()
        region_val = tk.Label(pad_frame, textvariable=self._region_label_var,
                              font=("Consolas", 9), bg=BG, fg="#7ec87e",
                              anchor="w", width=24)
        region_val.grid(row=row, column=1, sticky="w", pady=3)

        drag_btn = tk.Button(
            pad_frame, text="Select", width=6, font=("Arial", 9),
            bg="#3a5e8a", fg="#ffffff", activebackground="#4a7eba",
            relief="flat", command=self._pick_ocr_region,
        )
        drag_btn.grid(row=row, column=2, sticky="e", pady=3, padx=(4, 0))
        row += 1

        # ── Action buttons ──
        btn_frame = tk.Frame(pad_frame, bg=BG)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(14, 0))

        save_btn = tk.Button(
            btn_frame, text="Save", width=10, font=("Arial", 10, "bold"),
            bg="#3a6e3a", fg="#ffffff", activebackground="#4e8e4e",
            relief="flat", command=self._on_save,
        )
        save_btn.pack(side="left", padx=4)

        defaults_btn = tk.Button(
            btn_frame, text="Defaults", width=10, font=("Arial", 10),
            bg="#555555", fg="#ffffff", activebackground="#6e6e6e",
            relief="flat", command=self._on_defaults,
        )
        defaults_btn.pack(side="left", padx=4)

        cancel_btn = tk.Button(
            btn_frame, text="Cancel", width=10, font=("Arial", 10),
            bg="#555555", fg="#ffffff", activebackground="#6e6e6e",
            relief="flat", command=self.destroy,
        )
        cancel_btn.pack(side="left", padx=4)

    def _refresh_region_label(self):
        l, t, r, b = self._ocr_region
        self._region_label_var.set(f"({l:.2f},{t:.2f})-({r:.2f},{b:.2f})")

    def _get_screenshot_or_warn(self):
        """Capture the Roblox window. Returns (pil_img, win) or None."""
        win = find_roblox_window()
        if win is None:
            update_status(f"Cannot find a window titled \"{config['window_title']}\"")
            return None
        try:
            img = capture_full_window(win)
        except Exception as e:
            update_status(f"Screenshot failed: {e}")
            return None
        return img, win

    def _pick_click_pos(self):
        result = self._get_screenshot_or_warn()
        if result is None:
            return
        img, win = result
        self.grab_release()
        ScreenPicker(self, img, (win.width, win.height), mode="click",
                     callback=self._on_click_picked,
                     current_click=self._click_pos)

    def _on_click_picked(self, pos):
        self._click_pos = pos
        self._click_label_var.set(f"({pos[0]:.2f}, {pos[1]:.2f})")
        self.grab_set()

    def _pick_ocr_region(self):
        result = self._get_screenshot_or_warn()
        if result is None:
            return
        img, win = result
        self.grab_release()
        ScreenPicker(self, img, (win.width, win.height), mode="drag",
                     callback=self._on_region_picked,
                     current_region=self._ocr_region)

    def _on_region_picked(self, region):
        self._ocr_region = region
        self._refresh_region_label()
        self.grab_set()

    def _on_defaults(self):
        for key, _, _ in self.TEXT_FIELDS:
            entry = self.entries[key]
            entry.delete(0, tk.END)
            entry.insert(0, str(DEFAULTS[key]))
        self._click_pos = (DEFAULTS["input_click_x"], DEFAULTS["input_click_y"])
        self._click_label_var.set(f"({self._click_pos[0]:.2f}, {self._click_pos[1]:.2f})")
        self._ocr_region = (DEFAULTS["ocr_left"], DEFAULTS["ocr_top"],
                            DEFAULTS["ocr_right"], DEFAULTS["ocr_bottom"])
        self._refresh_region_label()

    def _on_save(self):
        old_hotkey = config["auto_hotkey"]
        old_full_hotkey = config["full_auto_hotkey"]
        old_loop_hotkey = config["loop_hotkey"]
        for key, label, typ in self.TEXT_FIELDS:
            raw = self.entries[key].get().strip()
            try:
                config[key] = typ(raw)
            except ValueError:
                update_status(f"Invalid value for {label}: {raw}")
                return

        config["input_click_x"] = self._click_pos[0]
        config["input_click_y"] = self._click_pos[1]
        config["ocr_left"] = self._ocr_region[0]
        config["ocr_top"] = self._ocr_region[1]
        config["ocr_right"] = self._ocr_region[2]
        config["ocr_bottom"] = self._ocr_region[3]

        save_config()

        if config["auto_hotkey"] != old_hotkey:
            keyboard.remove_hotkey(old_hotkey)
            keyboard.add_hotkey(
                config["auto_hotkey"],
                lambda: threading.Thread(target=auto_smalltalk, daemon=True).start(),
            )

        if config["full_auto_hotkey"] != old_full_hotkey:
            keyboard.remove_hotkey(old_full_hotkey)
            keyboard.add_hotkey(
                config["full_auto_hotkey"],
                lambda: threading.Thread(target=full_auto_smalltalk, daemon=True).start(),
            )

        if config["loop_hotkey"] != old_loop_hotkey:
            keyboard.remove_hotkey(old_loop_hotkey)
            keyboard.add_hotkey(config["loop_hotkey"], toggle_loop)

        if gui_app is not None:
            gui_app.refresh_auto_label()

        update_status("Settings saved")
        self.destroy()


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Deepwoken Charisma Helper")
        self.geometry("550x500")
        self.configure(bg="#2b2b2b")

        BG = "#2b2b2b"

        # ── Header ──
        header = tk.Label(
            self, text="Charisma Catchphrases", font=("Arial", 14, "bold"),
            bg=BG, fg="#ffffff",
        )
        header.pack(pady=(12, 4))

        # ── Manual hotkeys list ──
        self.listbox = tk.Listbox(
            self, width=64, height=10, font=("Consolas", 11),
            bg="#1e1e1e", fg="#d4d4d4", selectbackground="#3a3a3a",
            borderwidth=0, highlightthickness=0,
        )
        self.listbox.pack(pady=(4, 8))
        for i, phrase in enumerate(CATCHPHRASES):
            self.listbox.insert(tk.END, f"  {PREFIX}{i+1})  {phrase}")

        # ── Separator ──
        tk.Frame(self, height=1, bg="#555555").pack(fill="x", padx=16, pady=4)

        # ── Auto mode info ──
        self.auto_label_var = tk.StringVar()
        self._update_auto_label_text()
        auto_label = tk.Label(
            self, textvariable=self.auto_label_var,
            font=("Arial", 11, "bold"), bg=BG, fg="#7ec87e",
        )
        auto_label.pack(pady=(8, 2))

        auto_desc = tk.Label(
            self,
            text=("F1: OCR + type + submit  |  "
                  "F2: full auto (once)  |  F3: full auto loop"),
            font=("Arial", 9), bg=BG, fg="#aaaaaa", wraplength=500,
        )
        auto_desc.pack(pady=(0, 6))

        # ── Settings button ──
        settings_btn = tk.Button(
            self, text="Settings", width=14, font=("Arial", 10),
            bg="#555555", fg="#ffffff", activebackground="#6e6e6e",
            relief="flat", command=self._open_settings,
        )
        settings_btn.pack(pady=(0, 8))

        # ── Status bar ──
        self.status_var = tk.StringVar(
            value=f"Ready — {config['auto_hotkey']}: OCR only | {config['full_auto_hotkey']}: full auto")
        self.status_label = tk.Label(
            self, textvariable=self.status_var, font=("Consolas", 10),
            bg="#1e1e1e", fg="#cccccc", anchor="w", padx=8, pady=4,
        )
        self.status_label.pack(fill="x", side="bottom", padx=8, pady=(0, 8))

        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _update_auto_label_text(self):
        self.auto_label_var.set(
            f"[ {config['auto_hotkey']} ] OCR    "
            f"[ {config['full_auto_hotkey']} ] Full    "
            f"[ {config['loop_hotkey']} ] Loop")

    def refresh_auto_label(self):
        self._update_auto_label_text()

    def _open_settings(self):
        SettingsDialog(self)

    def set_status(self, msg):
        self.status_var.set(msg)

    def on_close(self):
        self.destroy()


def run_gui():
    global gui_app
    gui_app = MainWindow()
    gui_app.mainloop()


def main():
    load_config()
    hotkey_thread = threading.Thread(target=setup_hotkeys, daemon=True)
    hotkey_thread.start()
    run_gui()


if __name__ == "__main__":
    main()