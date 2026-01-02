#!/usr/bin/env python3
"""OTB Chess video listener for macOS.

- Watches the inbox folder for new videos (default: ~/OTBReview/inbox).
- Moves each new file to a timestamped work directory.
- Writes a manifest.json with metadata and hashes to prevent duplicates.
- Triggers `otbreview analyze --input <file>` and logs output.
"""

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

try:
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
    from watchdog.observers import Observer
except ImportError as exc:  # pragma: no cover - handled at runtime
    print("watchdog is required: pip install watchdog", file=sys.stderr)
    raise

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
DEFAULT_BASE = Path.home() / "OTBReview"
LOG_FILE_NAME = "otb_listener.log"
PROCESSED_DB_NAME = "processed.json"


def ensure_directories(base: Path) -> None:
    for sub in ["inbox", "work", "logs"]:
        (base / sub).mkdir(parents=True, exist_ok=True)


def load_processed(db_path: Path) -> Dict[str, Dict[str, str]]:
    if not db_path.exists():
        return {}
    try:
        with db_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data.get("processed", {}) if isinstance(data.get("processed", {}), dict) else {}
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to read processed db %s: %s", db_path, exc)
    return {}


def save_processed(db_path: Path, processed: Dict[str, Dict[str, str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"processed": processed}
    tmp = db_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(db_path)


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe_metadata(path: Path) -> Dict[str, Optional[str]]:
    """Return duration/resolution/fps when ffprobe is available."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        duration = None
        width = None
        height = None
        fps = None
        if "format" in payload and "duration" in payload["format"]:
            try:
                duration = float(payload["format"]["duration"])
            except (TypeError, ValueError):
                duration = None
        streams = payload.get("streams", [])
        if streams:
            stream = streams[0]
            width = stream.get("width")
            height = stream.get("height")
            fps_raw = stream.get("r_frame_rate")
            if fps_raw and "/" in fps_raw:
                num, denom = fps_raw.split("/", 1)
                try:
                    fps = float(num) / float(denom)
                except (TypeError, ValueError, ZeroDivisionError):
                    fps = None
        return {
            "duration_seconds": duration,
            "width": width,
            "height": height,
            "fps": fps,
        }
    except FileNotFoundError:
        logging.info("ffprobe not found; metadata will be partial")
    except subprocess.CalledProcessError as exc:
        logging.warning("ffprobe failed for %s: %s", path, exc)
    return {
        "duration_seconds": None,
        "width": None,
        "height": None,
        "fps": None,
    }


def build_manifest(source: Path, dest: Path, sha256: str) -> Dict[str, object]:
    stat = dest.stat()
    recorded_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
    meta = ffprobe_metadata(dest)
    manifest = {
        "source_filename": source.name,
        "destination": str(dest),
        "sha256": sha256,
        "recorded_at": recorded_at,
        "size_bytes": stat.st_size,
        **meta,
    }
    return manifest


def analyze_video(video_path: Path, base_dir: Path, analyze_cmd: Optional[str]) -> int:
    if analyze_cmd:
        command = analyze_cmd.format(input=str(video_path))
        cmd = ["bash", "-lc", command]
    else:
        cmd = ["otbreview", "analyze", "--input", str(video_path)]
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"analyze-{video_path.parent.name}.log"
    with log_file.open("w", encoding="utf-8") as lf:
        lf.write(f"Running: {' '.join(cmd)}\n")
        lf.flush()
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
    logging.info("Analysis finished with code %s for %s", proc.returncode, video_path)
    return proc.returncode


def move_and_process(
    path: Path,
    base_dir: Path,
    processed: Dict[str, Dict[str, str]],
    analyze_cmd: Optional[str],
    processed_db: Path,
) -> None:
    if not path.exists():
        logging.debug("Path %s disappeared before processing", path)
        return
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        logging.debug("Ignoring non-video file %s", path)
        return
    try:
        file_hash = sha256sum(path)
    except Exception as exc:  # pragma: no cover
        logging.error("Failed to hash %s: %s", path, exc)
        return
    if file_hash in processed:
        logging.info("Skipping already processed file %s", path)
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_dir = base_dir / "work" / timestamp
    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / Path("game").with_suffix(path.suffix.lower())

    logging.info("Moving %s to %s", path, dest)
    try:
        shutil.move(str(path), dest)
    except Exception as exc:  # pragma: no cover
        logging.error("Failed to move %s -> %s: %s", path, dest, exc)
        return

    manifest = build_manifest(path, dest, file_hash)
    with (work_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    processed[file_hash] = {
        "source": str(path),
        "destination": str(dest),
        "timestamp": timestamp,
    }
    save_processed(processed_db, processed)

    analyze_video(dest, base_dir, analyze_cmd)


def process_existing(
    inbox: Path,
    base_dir: Path,
    processed: Dict[str, Dict[str, str]],
    analyze_cmd: Optional[str],
    processed_db: Path,
) -> None:
    for item in sorted(inbox.iterdir()):
        if item.is_file():
            move_and_process(item, base_dir, processed, analyze_cmd, processed_db)


class InboxHandler(FileSystemEventHandler):
    def __init__(
        self,
        inbox: Path,
        base_dir: Path,
        processed: Dict[str, Dict[str, str]],
        analyze_cmd: Optional[str],
        processed_db: Path,
    ):
        super().__init__()
        self.inbox = inbox
        self.base_dir = base_dir
        self.processed = processed
        self.analyze_cmd = analyze_cmd
        self.processed_db = processed_db

    def on_created(self, event: FileCreatedEvent):  # type: ignore[override]
        if event.is_directory:
            return
        time.sleep(0.5)  # allow writes to finish
        move_and_process(
            Path(event.src_path), self.base_dir, self.processed, self.analyze_cmd, self.processed_db
        )

    def on_moved(self, event: FileMovedEvent):  # type: ignore[override]
        if event.is_directory:
            return
        time.sleep(0.5)
        move_and_process(
            Path(event.dest_path), self.base_dir, self.processed, self.analyze_cmd, self.processed_db
        )


def configure_logging(base_dir: Path, verbose: bool) -> None:
    log_file = base_dir / "logs" / LOG_FILE_NAME
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(log_file)]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch inbox for new OTB videos and analyze")
    parser.add_argument("--inbox", type=Path, default=DEFAULT_BASE / "inbox", help="Folder to watch for new videos")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE, help="Base directory for work/logs")
    parser.add_argument("--analyze-cmd", type=str, default=None, help="Custom analyze command template; use {input} placeholder")
    parser.add_argument("--oneshot", action="store_true", help="Process current files then exit")
    parser.add_argument("--verbose", action="store_true", help="Print logs to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_directories(args.base)
    configure_logging(args.base, args.verbose)

    inbox = args.inbox.expanduser()
    base_dir = args.base.expanduser()
    inbox.mkdir(parents=True, exist_ok=True)

    logging.info("Starting listener on %s", inbox)
    processed_db = base_dir / "logs" / PROCESSED_DB_NAME
    processed = load_processed(processed_db)

    process_existing(inbox, base_dir, processed, args.analyze_cmd, processed_db)
    if args.oneshot:
        return 0

    event_handler = InboxHandler(inbox, base_dir, processed, args.analyze_cmd, processed_db)
    observer = Observer()
    observer.schedule(event_handler, str(inbox), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping listener")
    finally:
        observer.stop()
        observer.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
