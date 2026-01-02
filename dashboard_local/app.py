from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

from dashboard_local.utils import (
    create_run_dir,
    discover_runs,
    key_artifacts,
    load_run_metadata,
    run_status,
    save_uploaded_file,
    stream_process,
    write_run_metadata,
    zip_run_directory,
)


st.set_page_config(page_title="OTBReview Beginner Dashboard", layout="wide")


def _stream_logs(cmd):
    log_placeholder = st.empty()
    log_lines = []
    process_stream = stream_process(cmd)
    for line in process_stream:
        log_lines.append(line)
        log_placeholder.code("\n".join(log_lines[-200:]), language="bash")
    if log_lines:
        log_placeholder.code("\n".join(log_lines[-200:]), language="bash")
    return getattr(process_stream, "returncode", 0), "\n".join(log_lines)


def run_marker_pipeline(input_path: Path, run_dir: Path, fps: float, save_debug: bool) -> bool:
    st.write("### Running Marker Mode…")
    cmd = [
        "python",
        "scripts/run_debug_pipeline.py",
        "--input",
        str(input_path),
        "--outdir",
        str(run_dir),
        "--use_markers",
        "1",
        "--fps",
        str(fps),
    ]
    code, logs = _stream_logs(cmd)
    st.write("### Generating CHECK.html…")
    report_cmd = ["python", "scripts/make_check_report.py", "--outdir", str(run_dir)]
    code2, logs2 = _stream_logs(report_cmd)
    return code == 0 and code2 == 0 and "fail" not in (logs + logs2).lower()


def run_tag_pipeline(input_path: Path, run_dir: Path, fps: float, save_debug: bool) -> bool:
    st.write("### Running Tag Mode…")
    cmd = [
        "python",
        "scripts/run_tag_demo.py",
        "--input",
        str(input_path),
        "--outdir",
        str(run_dir),
        "--fps",
        str(fps),
    ]
    if not save_debug:
        cmd.append("--no-save-debug")
    code, logs = _stream_logs(cmd)
    return code == 0 and "fail" not in logs.lower()


def sidebar_history():
    st.sidebar.title("Runs history")
    runs = discover_runs()
    if not runs:
        st.sidebar.info("No runs yet")
        return None
    labels = []
    mapping = {}
    for run_id, path in runs:
        meta = load_run_metadata(path)
        status = run_status(path)
        name = meta.get("input_file", path.name)
        ts = meta.get("timestamp", run_id)
        label = f"{run_id} | {name} | {status}"
        labels.append(label)
        mapping[label] = path
        st.sidebar.write(f"**{run_id}**  ")
        st.sidebar.caption(f"{name} • {ts} • {status}")
    selected = st.sidebar.radio("Select a run to open", labels, index=0 if labels else None)
    st.sidebar.markdown("---")
    return mapping.get(selected)


def show_results(run_dir: Path):
    meta = load_run_metadata(run_dir)
    st.subheader(f"Run: {run_dir.name}")
    st.caption(
        f"Input: {meta.get('input_file', 'unknown')} • Mode: {meta.get('mode', 'n/a')} • Timestamp: {meta.get('timestamp', '')}"
    )

    artifacts = key_artifacts(run_dir)
    cols = st.columns(3)
    for idx, key in enumerate(["stable", "warped", "grid", "aruco", "tag_overlay", "tag_zoom", "tag_grid"]):
        if artifacts.get(key):
            cols[idx % 3].image(str(artifacts[key]), caption=Path(artifacts[key]).name, use_column_width=True)

    reports = []
    if (run_dir / "TAG_CHECK.html").exists():
        reports.append(("TAG_CHECK", run_dir / "TAG_CHECK.html"))
    if (run_dir / "CHECK.html").exists():
        reports.append(("CHECK", run_dir / "CHECK.html"))

    for title, path in reports:
        st.markdown(f"#### {title}")
        try:
            st.components.v1.html(path.read_text(encoding="utf-8", errors="ignore"), height=600, scrolling=True)
        except Exception:
            st.warning("Preview not available; open in browser below")
        st.markdown(f"[Open in browser]({path.resolve().as_uri()})")

    st.markdown("### Downloads")
    zip_bytes = zip_run_directory(run_dir)
    st.download_button("Download full ZIP", data=zip_bytes, file_name=f"{run_dir.name}.zip")
    for fname in ["game.pgn", "board_ids.json", "debug/board_ids.json", "debug/tag_metrics.csv"]:
        fpath = run_dir / fname
        if fpath.exists():
            with open(fpath, "rb") as f:
                st.download_button(f"Download {fname}", data=f, file_name=fpath.name, key=f"dl-{fname}")


def upload_and_run(selected_run: Optional[Path]):
    st.header("Upload & Run")
    uploaded_file = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "MP4", "MOV", "MKV"])
    mode = st.radio("Mode", ["Marker mode (corners only)", "Tag mode (corners + piece tags)"])
    fps = st.number_input("FPS for stable frames", min_value=1.0, max_value=12.0, value=3.0, step=0.5)
    save_debug = st.checkbox("Save debug overlays", value=True)

    if st.button("Run", type="primary", use_container_width=True):
        if uploaded_file is None:
            st.error("Please upload a video first")
            return
        run_dir, run_id = create_run_dir()
        input_path = save_uploaded_file(uploaded_file, run_dir)
        write_run_metadata(
            run_dir,
            {
                "run_id": run_id,
                "input_file": uploaded_file.name,
                "mode": "Tag" if "Tag" in mode else "Marker",
                "timestamp": datetime.now().isoformat(),
            },
        )
        st.success(f"Saved upload to {input_path}")
        success = False
        if "Tag" in mode:
            success = run_tag_pipeline(input_path, run_dir, fps, save_debug)
        else:
            success = run_marker_pipeline(input_path, run_dir, fps, save_debug)

        st.session_state["selected_run"] = run_dir
        if success:
            st.success("Pipeline completed!")
        else:
            st.warning("Pipeline finished with warnings. Check logs and reports.")


def main():
    selected_from_sidebar = sidebar_history()
    tabs = st.tabs(["Upload & Run", "Results"])
    with tabs[0]:
        upload_and_run(selected_from_sidebar)
    with tabs[1]:
        run_dir: Optional[Path] = st.session_state.get("selected_run") or selected_from_sidebar
        if run_dir and Path(run_dir).exists():
            show_results(Path(run_dir))
        else:
            st.info("Select or create a run to view results")


if __name__ == "__main__":
    main()
