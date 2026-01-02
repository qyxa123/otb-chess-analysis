# OTB Chess Recorder (Mac + iPhone ingest)

A minimal offline pipeline to collect over-the-board chess videos on iPhone and analyze them on macOS with **zero in-game interaction** (start/stop only).

## Project structure

```
README.md                 # How to set up and test
scripts/otb_listener.py   # macOS watcher daemon
scripts/import_latest_ios.sh # (optional) USB pull via libimobiledevice/ifuse
launchd/com.otbreview.listener.plist # launchd service template
requirements_mac.txt      # Python deps for mac listener
```

## Prerequisites (macOS)
- Python 3.9+ and `pip`
- `ffmpeg` (for `ffprobe` metadata; install via `brew install ffmpeg`)
- `watchdog` Python lib (installed via `pip install -r requirements_mac.txt`)
- `otbreview` CLI available in `$PATH` (used by the analyzer command)
- Inbox/work/logs live at `~/OTBReview` by default

Optional for USB import:
- Homebrew packages: `libimobiledevice` and `ifuse` (`brew install libimobiledevice ifuse`)

## Quick start: process manually-dropped videos (most reliable path)
1. Prepare folders and deps:
   ```bash
   mkdir -p ~/OTBReview/inbox ~/OTBReview/work ~/OTBReview/logs
   pip install -r requirements_mac.txt
   ```
2. Run the listener (foreground, verbose):
   ```bash
   python scripts/otb_listener.py --verbose
   ```
3. Record a 10s video on iPhone, then AirDrop/drag it into `~/OTBReview/inbox/`.
4. Expected behavior:
   - File is moved to `~/OTBReview/work/<timestamp>/game.<ext>`
   - `manifest.json` appears alongside the video with hash + metadata
   - `otbreview analyze --input <file>` runs; logs land in `~/OTBReview/logs/analyze-<timestamp>.log`
   - Dedup: the same file (by SHA-256) will be skipped on re-drop.

To run once over existing files and exit:
```bash
python scripts/otb_listener.py --oneshot
```

## Automating ingestion from iPhone to `inbox`
Pick one approach; all are offline.

### 1) USB (libimobiledevice + ifuse) – script provided
```bash
brew install libimobiledevice ifuse
INBOX_DIR=~/OTBReview/inbox scripts/import_latest_ios.sh
```
- The script pairs the phone, mounts DCIM, copies the newest MOV/MP4 into the inbox, then unmounts.
- If pairing fails, confirm “Trust this computer” on iPhone and rerun.

You can cron/launchd this to poll every few minutes, or just run it after each game. Once the copy finishes, the watcher handles the rest.

### 2) Photos / Image Capture (no extra installs)
- Open **Image Capture** → select iPhone → set destination to `~/OTBReview/inbox/` → import the newest clip.
- You can automate with AppleScript (save as an app/shortcut):
  ```applescript
  tell application "Image Capture"
    set this_device to first device whose name contains "iPhone"
    set downloads folder to POSIX file (POSIX path of (path to home folder) & "OTBReview/inbox/")
    import first item of this_device
  end tell
  ```

### 3) Wireless (AirDrop / Shared Album / Shortcuts)
- **AirDrop**: send the video from Photos to the Mac; set default save location to `Downloads`, then run `mv ~/Downloads/*.MOV ~/OTBReview/inbox/` (or add a Folder Action/Shortcut to auto-move).
- **Shortcuts on iPhone** (optional enhancement):
  - Action chain: *Record Video* → *Save File* (target iCloud Drive `OTBReviewInbox/`) → *Show Notification*.
  - On Mac, sync iCloud Drive and set a Folder Action/launchd to `mv ~/Library/Mobile\ Documents/com~apple~CloudDocs/OTBReviewInbox/* ~/OTBReview/inbox/`.

## launchd autostart
Template: `launchd/com.otbreview.listener.plist`
1. Edit `REPLACE_ME` to your mac username and repository path.
2. Copy into `~/Library/LaunchAgents/`:
   ```bash
   cp launchd/com.otbreview.listener.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.otbreview.listener.plist
   launchctl start com.otbreview.listener
   ```
3. Logs: `~/OTBReview/logs/launchd.out.log` and `launchd.err.log`.

## How it works
- Watches `~/OTBReview/inbox` (watchdog). New video triggers:
  1) SHA-256 check against `~/OTBReview/logs/processed.json` to avoid repeats.
  2) Move to `~/OTBReview/work/<timestamp>/game.<ext>`.
  3) Write `manifest.json` (hash, size, recorded_at, duration/resolution/fps when `ffprobe` exists).
  4) Run `otbreview analyze --input <file>`; capture stdout/stderr to `logs/analyze-<timestamp>.log`.
- If metadata or analysis fails, the script keeps the video and logs the error; you can re-run with `--oneshot` after fixing dependencies.

## Troubleshooting / fallback
- **watchdog missing**: `pip install watchdog`
- **ffprobe missing**: install ffmpeg; manifest will show nulls until then.
- **Permission pairing**: run `idevicepair pair` and accept trust on iPhone.
- **Manual fallback**: dragging any video into `~/OTBReview/inbox/` always triggers processing—no other dependencies.

## Testing checklist (10s smoke test)
1. Start listener: `python scripts/otb_listener.py --verbose`
2. Drop a 10s iPhone clip into `~/OTBReview/inbox/`.
3. Verify:
   - `~/OTBReview/work/<timestamp>/game.mov` exists
   - `manifest.json` contains `sha256` and (when ffprobe present) duration/resolution/fps
   - `logs/analyze-<timestamp>.log` shows `otbreview analyze --input ...` ran

## Optional enhancements
- Run `scripts/import_latest_ios.sh` via `launchd` every 2 minutes to auto-pull the latest clip over USB.
- Create an iPhone Shortcut: “Start Recording → Save to iCloud Drive OTBReviewInbox → Notify done” so the Mac ingests automatically from synced folder.
