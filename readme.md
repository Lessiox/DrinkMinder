# DrinkMinder 💧

A lightweight Windows desktop app that reminds you to drink water during work hours. The reminder popup locks your screen for a few seconds — forcing you to take a break and hydrate.

> **Note:** ~90% of this project's code was generated with AI assistance (GitHub Copilot / Claude).

## Features

- **Scheduled reminders** — popups appear at regular intervals (e.g. every 15 min) during configurable work hours
- **Forced hydration break** — the popup is always-on-top with no close/minimize button; you must wait for the countdown to finish and press Ok
- **System tray icon** — runs silently in the background with a tray icon showing the next reminder time
- **Settings window** — configure everything from the app UI (no need to edit files manually)
- **Multi-language** — supports Italian and English, switchable from settings
- **Portable config** — reads/writes a `config.ini` file next to the executable; auto-creates defaults on first run
- **Rounded corners** — native Windows 11 rounded window corners via DWM API

## Configuration

All settings are stored in `config.ini` (auto-created on first run):

```ini
[DrinkMinder]
work_ranges = 9-13, 14-18
reminder_interval = 15
lock_seconds = 10
debug = false
language = it
```

| Setting | Description | Default |
|---|---|---|
| `work_ranges` | Hour ranges when reminders are active (comma separated) | `9-13, 14-18` |
| `reminder_interval` | Minutes between reminders | `15` |
| `lock_seconds` | Seconds the popup stays locked before you can dismiss it | `10` |
| `debug` | If `true`, shows a reminder immediately on startup | `false` |
| `language` | UI language (`it` or `en`) | `it` |

You can also change all settings from the ⚙ button in the app or the tray menu. Changes take effect immediately.

## Installation

### From source

```bash
pip install customtkinter pystray Pillow
python DrinkMinder.py
```

### Build standalone executable

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --noconfirm --name DrinkMinder --icon=drinkminder_icon.ico --add-data "drinkminder_icon.ico;." DrinkMinder.py
```

The executable will be in `dist/DrinkMinder.exe`. Place `config.ini` next to it (or let the app create a default one on first run).

## Requirements

- Python 3.10+
- Windows 10/11
- Dependencies: `customtkinter`, `pystray`, `Pillow`

## Credits

- App icon by [Elegantthemes](https://icon-icons.com/it/authors/103-elegantthemes), sourced from [icon-icons.com](https://icon-icons.com/it/icona/acqua/23838), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Code largely generated with AI assistance (GitHub Copilot / Claude)

## License

MIT
