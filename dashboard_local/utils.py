import io
import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

BASE_OUTDIR = Path("out/web_runs")


def ensure_base_outdir() -> Path:
    BASE_OUTDIR.mkdir(parents=True, exist_ok=True)
    return BASE_OUTDIR


def create_run_dir() -> Tuple[Path, str]:
    ensure_base_outdir()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = BASE_OUTDIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_id


def save_uploaded_file(uploaded_file, run_dir: Path) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    dest = run_dir / f"input{suffix}"
    with dest.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def stream_process(command: List[str], cwd: Optional[Path] = None) -> Generator[str, None, None]:
    """Run a subprocess and yield log lines as they appear."""

    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def generator() -> Generator[str, None, None]:
        if process.stdout:
            for line in process.stdout:
                yield line.rstrip("\n")
        process.wait()
        generator.returncode = process.returncode

    generator.returncode = None  # type: ignore[attr-defined]
    return generator()


def load_run_metadata(run_dir: Path) -> Dict:
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_run_metadata(run_dir: Path, data: Dict) -> None:
    meta_path = run_dir / "run_meta.json"
    try:
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def discover_runs() -> List[Tuple[str, Path]]:
    ensure_base_outdir()
    runs = []
    for child in BASE_OUTDIR.iterdir():
        if child.is_dir():
            runs.append((child.name, child))
    runs.sort(reverse=True)
    return runs


def parse_check_status(check_path: Path) -> Optional[str]:
    if not check_path.exists():
        return None
    try:
        content = check_path.read_text(encoding="utf-8", errors="ignore").lower()
        if "status-pass" in content or "验收通过" in content or "pass" in content:
            return "PASS"
        if "status-fail" in content or "fail" in content or "未通过" in content:
            return "FAIL"
    except Exception:
        return None
    return None


def parse_tag_status(tag_path: Path) -> Optional[str]:
    if not tag_path.exists():
        return None
    content = tag_path.read_text(encoding="utf-8", errors="ignore").lower()
    if "pass" in content and "needs attention" not in content:
        return "PASS"
    if "need" in content or "fail" in content:
        return "FAIL"
    return None


def list_artifacts(run_dir: Path) -> List[Tuple[str, Path]]:
    artifacts = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(run_dir)
            if rel.name == "run_meta.json":
                continue
            artifacts.append((str(rel), path))
    return artifacts


def find_first_image(directory: Path) -> Optional[Path]:
    if not directory.exists():
        return None
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def key_artifacts(run_dir: Path) -> Dict[str, Optional[Path]]:
    debug = run_dir / "debug"
    return {
        "stable": find_first_image(debug / "stable_frames"),
        "warped": find_first_image(debug / "warped_boards"),
        "grid": debug / "grid_overlay.png" if (debug / "grid_overlay.png").exists() else None,
        "aruco": debug / "aruco_preview.png" if (debug / "aruco_preview.png").exists() else None,
        "tag_overlay": debug / "tag_overlay_0001.png" if (debug / "tag_overlay_0001.png").exists() else None,
        "tag_zoom": debug / "tag_overlay_zoom_0001.png" if (debug / "tag_overlay_zoom_0001.png").exists() else None,
        "tag_grid": debug / "tag_grid_0001.png" if (debug / "tag_grid_0001.png").exists() else None,
    }


def run_status(run_dir: Path) -> str:
    tag_status = parse_tag_status(run_dir / "TAG_CHECK.html")
    check_status = parse_check_status(run_dir / "CHECK.html")
    return tag_status or check_status or "PENDING"


def zip_run_directory(run_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(run_dir))
    buffer.seek(0)
    return buffer.read()
