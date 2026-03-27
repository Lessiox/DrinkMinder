import customtkinter as ctk
from datetime import datetime, timedelta
import threading
import configparser
import sys
import os
import ctypes
from PIL import Image, ImageDraw, ImageFont
import pystray

# --- Carica configurazione da config.ini ---
def get_config_path():
    """Restituisce il percorso di config.ini accanto all'exe o allo script."""
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
    }

config = load_config()
WORK_RANGES = config["work_ranges"]
REMINDER_INTERVAL = config["reminder_interval"]
LOCK_SECONDS = config["lock_seconds"]
DEBUG_MODE = config["debug"]

tray_icon = None
next_trigger_label = ""
reminder_active = False  # True mentre il reminder è visibile (blocca nuovi trigger)

def is_work_time(now=None):
    if now is None:
        now = datetime.now()
    hour = now.hour
    return any(start <= hour < end for start, end in WORK_RANGES)

def next_trigger_time():
    """Calcola il prossimo slot allineato a REMINDER_INTERVAL in fascia lavorativa."""
    now = datetime.now()
    # Prossimo slot allineato (es. ogni 5 min: :00, :05, :10, ...)
    minutes_since_midnight = now.hour * 60 + now.minute
    next_slot = (minutes_since_midnight // REMINDER_INTERVAL + 1) * REMINDER_INTERVAL
    candidate = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=next_slot)

    # Cerca il primo slot in fascia lavorativa (copre 24h intere)
    max_iterations = (24 * 60) // REMINDER_INTERVAL + 1
    for _ in range(max_iterations):
        if is_work_time(candidate):
            return candidate
        candidate += timedelta(minutes=REMINDER_INTERVAL)
    return None

def ms_until(target):
    """Millisecondi da adesso fino a target."""
    delta = (target - datetime.now()).total_seconds()
    return max(int(delta * 1000), 0)

def set_rounded_corners(win):
    """Applica bordi arrotondati su Windows 11 tramite DWM."""
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
        )
    except Exception:
        pass  # Non Windows 11, ignora silenziosamente

def center_window(win, width, height):
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")

def block_close():
    """Impedisce la chiusura della finestra."""
    pass

def show_reminder():
    """Mostra la finestra bloccata per LOCK_SECONDS secondi."""
    global reminder_active
    reminder_active = True
    countdown_var.set(LOCK_SECONDS)
    buttonOk.configure(state="disabled", text=f"Attendi {LOCK_SECONDS}s...")
    app.deiconify()
    center_window(app, 400, 220)
    app.overrideredirect(True)
    app.protocol("WM_DELETE_WINDOW", block_close)
    app.attributes("-topmost", True)
    app.focus_force()
    tick_countdown()

def tick_countdown():
    """Aggiorna il conto alla rovescia ogni secondo."""
    remaining = countdown_var.get()
    if remaining > 1:
        countdown_var.set(remaining - 1)
        buttonOk.configure(text=f"Attendi {remaining - 1}s...")
        app.after(1000, tick_countdown)
    else:
        buttonOk.configure(state="normal", text="Ok ✓")

def hide_and_schedule():
    """Nasconde la finestra, calcola il prossimo slot e riavvia il polling."""
    global reminder_active
    reminder_active = False
    app.overrideredirect(False)
    app.attributes("-topmost", False)
    app.protocol("WM_DELETE_WINDOW", lambda: None)
    app.withdraw()
    update_next_trigger_label()
    start_polling()

def update_next_trigger_label():
    """Aggiorna il tooltip della tray con il prossimo slot."""
    global next_trigger_label
    target = next_trigger_time()
    if target:
        next_trigger_label = target.strftime("%H:%M")
    else:
        next_trigger_label = "nessun trigger"
    update_tray_tooltip()

def start_polling():
    """Avvia il controllo periodico ogni 30 secondi."""
    check_trigger()

def check_trigger():
    """Controlla periodicamente se è il momento di mostrare un reminder."""
    if reminder_active:
        return  # Non fare nulla mentre il reminder è visibile
    now = datetime.now()
    if is_work_time(now) and now.minute % REMINDER_INTERVAL == 0 and now.second < 30:
        show_reminder()
        return  # Stop polling, ripartirà dopo Ok
    app.after(10000, check_trigger)  # Ricontrolla fra 10 secondi

# --- System Tray ---
def create_tray_icon_image():
    """Genera un'icona 64x64 con l'emoji 💧."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("seguiemj.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((8, 0), "💧", font=font, embedded_color=True)
    return img

def update_tray_tooltip():
    """Aggiorna il tooltip della tray icon."""
    if tray_icon:
        tray_icon.title = f"DrinkMinder — prossimo reminder: {next_trigger_label}"

def quit_app(icon, item):
    """Chiude completamente l'app dalla tray."""
    icon.stop()
    app.after(0, app.destroy)

def start_tray():
    """Avvia la tray icon in un thread separato."""
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem(lambda text: f"Prossimo reminder: {next_trigger_label}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Esci da DrinkMinder", quit_app),
    )
    tray_icon = pystray.Icon("DrinkMinder", create_tray_icon_image(), f"DrinkMinder — prossimo reminder: {next_trigger_label}", menu)
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
    text="💧 Bevi un po' d'acqua! 💧",
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
    text=f"DrinkMinder attivo — reminder ogni {REMINDER_INTERVAL} min",
    font=("Helvetica", 12),
    text_color="gray",
)
status_label.pack(pady=(0, 10))

buttonOk = ctk.CTkButton(app, text="Attendi...", command=hide_and_schedule, state="disabled", fg_color="#1E90FF", hover_color="#22658B", font=("Helvetica", 14))
buttonOk.pack(pady=20, padx=20, fill="x")

# All'avvio: se siamo in fascia lavorativa e su uno slot, mostra subito
now = datetime.now()
if DEBUG_MODE:
    show_reminder()
else:
    app.withdraw()
    update_next_trigger_label()
    start_polling()

# Avvia tray icon in background
tray_thread = threading.Thread(target=start_tray, daemon=True)
tray_thread.start()

app.mainloop()  