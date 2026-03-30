import customtkinter as ctk
from datetime import datetime, timedelta
import threading
import configparser
import sys
import os
import ctypes
from PIL import Image, ImageDraw, ImageFont
import pystray

# --- Load configuration from config.ini ---
def get_config_path():
    """Return the path to config.ini next to the exe or script."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.ini")

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(get_config_path(), encoding="utf-8")
    section = cfg["DrinkMinder"] if "DrinkMinder" in cfg else {}

    ranges = []
    for r in section.get("work_ranges", "9-13, 14-18").split(","):
        start, end = r.strip().split("-")
        ranges.append((int(start), int(end)))

    return {
        "work_ranges": ranges,
        "reminder_interval": int(section.get("reminder_interval", "15")),
        "lock_seconds": int(section.get("lock_seconds", "10")),
        "debug": section.get("debug", "false").strip().lower() == "true",
        "language": section.get("language", "it").strip().lower(),
    }

# --- Translations ---
TRANSLATIONS = {
    "it": {
        "drink": "\U0001f4a7 Bevi un po' d'acqua! \U0001f4a7",
        "drink_short": "\U0001f4a7 Bevi un po' d'acqua!",
        "wait": "Attendi {s}s...",
        "ok": "Ok \u2713",
        "status": "DrinkMinder attivo \u2014 reminder ogni {m} min",
        "tray_next": "Prossimo reminder: {t}",
        "tray_tooltip": "DrinkMinder \u2014 prossimo reminder: {t}",
        "tray_quit": "Esci da DrinkMinder",
        "no_trigger": "nessun trigger",
    },
    "en": {
        "drink": "\U0001f4a7 Have a drink of water! \U0001f4a7",
        "drink_short": "\U0001f4a7 Have a drink of water!",
        "wait": "Wait {s}s...",
        "ok": "Ok \u2713",
        "status": "DrinkMinder active \u2014 reminder every {m} min",
        "tray_next": "Next reminder: {t}",
        "tray_tooltip": "DrinkMinder \u2014 next reminder: {t}",
        "tray_quit": "Quit DrinkMinder",
        "no_trigger": "no trigger",
    },
}

config = load_config()
WORK_RANGES = config["work_ranges"]
REMINDER_INTERVAL = config["reminder_interval"]
LOCK_SECONDS = config["lock_seconds"]
DEBUG_MODE = config["debug"]
LANG = config.get("language", "it")
STR = TRANSLATIONS.get(LANG, TRANSLATIONS["it"])

def t(key, **kwargs):
    return STR[key].format(**kwargs) if kwargs else STR[key]

tray_icon = None
next_trigger_label = ""
reminder_active = False

def is_work_time(now=None):
    if now is None:
        now = datetime.now()
    hour = now.hour
    return any(start <= hour < end for start, end in WORK_RANGES)

def next_trigger_time():
    """Calculate the next slot aligned to REMINDER_INTERVAL within work hours."""
    now = datetime.now()
    # Next aligned slot (e.g. every 5 min: :00, :05, :10, ...)
    minutes_since_midnight = now.hour * 60 + now.minute
    next_slot = (minutes_since_midnight // REMINDER_INTERVAL + 1) * REMINDER_INTERVAL
    candidate = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=next_slot)

    # Find the first slot within work hours (covers a full 24h cycle)
    max_iterations = (24 * 60) // REMINDER_INTERVAL + 1
    for _ in range(max_iterations):
        if is_work_time(candidate):
            return candidate
        candidate += timedelta(minutes=REMINDER_INTERVAL)
    return None

def ms_until(target):
    """Milliseconds from now until target."""
    delta = (target - datetime.now()).total_seconds()
    return max(int(delta * 1000), 0)

def set_rounded_corners(win):
    """Apply rounded corners on Windows 11 via DWM."""
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
        )
    except Exception:
        pass  # Not Windows 11, silently ignore

def center_window(win, width, height):
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")

def block_close():
    """Prevent window from being closed."""
    pass

def show_reminder():
    """Show the locked reminder window for LOCK_SECONDS seconds."""
    global reminder_active
    reminder_active = True
    countdown_var.set(LOCK_SECONDS)
    buttonOk.configure(state="disabled", text=t("wait", s=LOCK_SECONDS))
    app.deiconify()
    center_window(app, 400, 220)
    app.overrideredirect(True)
    app.protocol("WM_DELETE_WINDOW", block_close)
    app.attributes("-topmost", True)
    app.focus_force()
    tick_countdown()

def tick_countdown():
    """Update the countdown every second."""
    remaining = countdown_var.get()
    if remaining > 1:
        countdown_var.set(remaining - 1)
        buttonOk.configure(text=t("wait", s=remaining - 1))
        app.after(1000, tick_countdown)
    else:
        buttonOk.configure(state="normal", text=t("ok"))

def hide_and_schedule():
    """Hide the window, calculate the next slot and restart polling."""
    global reminder_active
    reminder_active = False
    app.overrideredirect(False)
    app.attributes("-topmost", False)
    app.protocol("WM_DELETE_WINDOW", lambda: None)
    app.withdraw()
    update_next_trigger_label()
    start_polling()

def update_next_trigger_label():
    """Update the tray tooltip with the next trigger slot."""
    global next_trigger_label
    target = next_trigger_time()
    if target:
        next_trigger_label = target.strftime("%H:%M")
    else:
        next_trigger_label = t("no_trigger")
    update_tray_tooltip()

def start_polling():
    """Start periodic trigger check."""
    check_trigger()

def check_trigger():
    """Periodically check if it's time to show a reminder."""
    if reminder_active:
        return  # Do nothing while a reminder is visible
    now = datetime.now()
    if is_work_time(now) and now.minute % REMINDER_INTERVAL == 0 and now.second < 30:
        show_reminder()
        return  # Stop polling, will restart after Ok
    app.after(10000, check_trigger)  # Recheck in 10 seconds

# --- System Tray ---
def create_tray_icon_image():
    """Generate a 64x64 icon with the 💧 emoji."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("seguiemj.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((8, 0), "💧", font=font, embedded_color=True)
    return img

def update_tray_tooltip():
    """Update the tray icon tooltip."""
    if tray_icon:
        tray_icon.title = t("tray_tooltip", t=next_trigger_label)

def quit_app(icon, item):
    """Fully quit the app from the tray."""
    icon.stop()
    app.after(0, app.destroy)

def start_tray():
    """Start the tray icon in a separate thread."""
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem(lambda text: t("tray_next", t=next_trigger_label), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("tray_quit"), quit_app),
    )
    tray_icon = pystray.Icon("DrinkMinder", create_tray_icon_image(), t("tray_tooltip", t=next_trigger_label), menu)
    tray_icon.run()

# --- Setup UI ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("DrinkMinder 💧")
app.minsize(400, 500)
app.update_idletasks()
set_rounded_corners(app)

countdown_var = ctk.IntVar(value=LOCK_SECONDS)

label = ctk.CTkLabel(
    app,
    text=t("drink"),
    font=("Helvetica", 24),
    corner_radius=20,
    fg_color="#1E90FF",
    text_color="white",
    wraplength=350,
    height=100,
)
label.pack(pady=30, padx=20, fill="x")

status_label = ctk.CTkLabel(
    app,
    text=t("status", m=REMINDER_INTERVAL),
    font=("Helvetica", 12),
    text_color="gray",
)
status_label.pack(pady=(0, 10))

buttonOk = ctk.CTkButton(app, text=t("wait", s="..."), command=hide_and_schedule, state="disabled", fg_color="#1E90FF", hover_color="#22658B", font=("Helvetica", 14))
buttonOk.pack(pady=20, padx=20, fill="x")

# On startup: if in work hours and on a slot, show immediately
now = datetime.now()
if DEBUG_MODE:
    show_reminder()
else:
    app.withdraw()
    update_next_trigger_label()
    start_polling()

# Start tray icon in background
tray_thread = threading.Thread(target=start_tray, daemon=True)
tray_thread.start()

app.mainloop()  