# LAN Messenger

A peer-to-peer Windows desktop chat app that works entirely over the local network —
no internet connection and no dedicated server required. Peers discover each other via
UDP broadcast, then chat and share files directly over TCP.

See `Building a Windows LAN Messenger – System Design and Implementation.pdf` for the full
design rationale, and `CLAUDE.md` for architecture notes if you're developing on this repo.

## Requirements

- Python 3.10+ (developed/tested on 3.13)
- `customtkinter` (the Windows-11-styled GUI) and `Pillow` (GUI icon images) — both installed
  via `requirements.txt`; everything else is standard library
  (`socket`, `json`, `sqlite3`, `tkinter`)
- Windows (Tkinter ships with the standard Windows Python installer; on other OSes it may
  need to be installed separately)

## Setup

Clone the repo and install the runtime dependencies plus the dev/build tooling (`pytest`,
`pyinstaller`) from `requirements.txt`, optionally inside a virtual environment:

```
git clone https://github.com/gitussr/lan-messenger.git
cd lan-messenger
pip install -r requirements.txt   # customtkinter + Pillow, plus pytest/pyinstaller/pytablericons for dev
```

## Running

```
python main.py [username]
```

If you omit the username, a small dialog window prompts for one — no console interaction is
needed anywhere in the app. Each running instance opens its own window and is simultaneously
a client and a server — there's nothing else to start.

To try it on one machine with two peers, open two terminals:

```
python main.py alice
python main.py bob
```

Give it a few seconds for discovery (peers re-announce every 5s); each window's contact
list should then show the other. Select a contact, type a message, and press Enter or
Send. Use the 📎 button to send a file — it lands in
`%USERPROFILE%\Downloads\LAN Messenger\<username>\`. Select the pinned "Broadcast to All"
entry to send one message to every discovered peer at once.

Chat history is stored locally per user in
`%LOCALAPPDATA%\LAN Messenger\<username>_chat_history.db` (SQLite) and is never shared with
other peers. Characters that aren't valid in Windows filenames are replaced with `_` in
these paths.

### Firewall

Windows Firewall may prompt to allow Python network access the first time you run this —
allow it on your private/home network profile. The app uses:

- UDP port `37020` for peer discovery
- A dynamically assigned TCP port per instance for chat/file transfer

## Testing

```
python -m pytest
```

Run a single test:

```
python -m pytest tests/test_storage.py -k round_trip
```

## Building a standalone .exe

```
pip install pyinstaller
pyinstaller --onedir --windowed --collect-data customtkinter --add-data "assets;assets" --exclude-module numpy --exclude-module PIL._avif --exclude-module PIL.AvifImagePlugin main.py
```

The build is a folder, `dist/main/`, containing `main.exe` and an `_internal/` folder of
support files. It runs on a machine without Python installed. To install it on another PC,
zip the whole `dist/main` folder (right-click → Send to → Compressed (zipped) folder), copy
the zip over, extract it, and run `main.exe`. Keep `_internal/` next to `main.exe`; the exe
won't start without it. A desktop shortcut to `main.exe` works fine.

Why a folder and not a single file: `--onefile` unpacks the whole bundle to a temp folder on
every launch, which took 7–10 seconds to open the window, compared with about 1–2 seconds
for the folder build.

`--collect-data customtkinter` bundles CustomTkinter's theme files, and `--add-data` bundles
the GUI icons in `assets/icons/`. The `--exclude-module` flags leave out Pillow extras the
app doesn't use (numpy support and AVIF images), which keeps the build small. The icons are
pre-rendered PNGs: to add or change one, edit `tools/render_icons.py` and run
`python tools/render_icons.py`.

`--windowed` matters: without it, `main.exe` keeps a console window attached, and closing
that console kills the whole app (including the chat window) since they're the same process.
