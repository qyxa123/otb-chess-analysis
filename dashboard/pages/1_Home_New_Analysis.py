from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from dashboard.utils import (
    create_run_dir,
    key_artifacts,
    load_board_grid,
    load_run_metadata,
    run_history,
    save_uploaded_file,
    stream_process,
    write_run_metadata,
)

st.title("Home / New Analysis")
st.caption("Upload, choose a mode, and click Analyze. Everything is saved automatically.")


def _stream_logs(cmd):
    placeholder = st.empty()
    logs = []
    process_stream = stream_process(cmd)
    for line in process_stream:
        logs.append(line)
        placeholder.code("\n".join(logs[-200:]), language="bash")
    placeholder.code("\n".join(logs[-200:]), language="bash")
    return getattr(process_stream, "returncode", 0), "\n".join(logs)


def _run_marker_pipeline(input_path: Path, run_dir: Path, fps: float, motion_threshold: float) -> bool:
    cmd = [
        sys.executable,
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
    st.info("Running marker pipeline…")
    code1, logs1 = _stream_logs(cmd)

    report_cmd = [sys.executable, "scripts/make_check_report.py", "--outdir", str(run_dir)]
    st.info("Generating CHECK.html…")
    code2, logs2 = _stream_logs(report_cmd)
    return code1 == 0 and code2 == 0 and "fail" not in (logs1 + logs2).lower()


def _run_tag_pipeline(
    input_path: Path,
    run_dir: Path,
    fps: float,
    motion_threshold: float,
    stable_duration: float,
    tag_sensitivity: float,
    enable_clahe: bool,
    enable_threshold: bool,
) -> bool:
    script_path = Path("scripts/run_tag_demo.py")
    if not script_path.exists():
        st.error("Tag pipeline script is missing.")
        return False
    cmd = [
        sys.executable,
        str(script_path),
        "--input",
        str(input_path),
        "--outdir",
        str(run_dir),
        "--fps",
        str(fps),
        "--motion-threshold",
        str(motion_threshold),
        "--stable-duration",
        str(stable_duration),
        "--tag-sensitivity",
        str(tag_sensitivity),
    ]
    if not enable_clahe:
        cmd.append("--disable-clahe")
    if not enable_threshold:
        cmd.append("--disable-threshold-path")
    st.info("Running tag pipeline…")
    code, logs = _stream_logs(cmd)
    return code == 0 and "fail" not in logs.lower()


with st.sidebar:
    st.markdown("### Recent runs")
    history = run_history()
    if not history:
        st.caption("No runs yet")
    else:
        for item in history[:10]:
            st.write(f"**{item['run_id']}** — {item.get('mode','')} {item.get('input_file','')}")

uploaded_file = st.file_uploader("Upload video", type=["mp4", "mov", "MP4", "MOV"])
mode = st.radio("Mode", ["Marker mode", "Tag mode"], horizontal=True)

with st.expander("Advanced", expanded=False):
    fps = st.slider("FPS sampling", 1.0, 12.0, 3.0, 0.5)
    motion_threshold = st.slider("Stability / motion threshold", 0.001, 0.05, 0.01, 0.001)
    stable_duration = st.slider("Stable duration (s)", 0.3, 1.5, 0.7, 0.1)
    tag_sensitivity = st.slider("Tag area sensitivity", 0.2, 2.0, 1.0, 0.1)
    enable_clahe = st.checkbox("Enable CLAHE enhancement", value=True)
    enable_threshold = st.checkbox("Enable adaptive threshold path", value=True)

run_clicked = st.button("Analyze", type="primary")

if run_clicked:
    if uploaded_file is None:
        st.error("Please upload a video first.")
    else:
        run_dir, run_id = create_run_dir()
        input_path = save_uploaded_file(uploaded_file, run_dir)
        write_run_metadata(
            run_dir,
            {
                "run_id": run_id,
                "input_file": uploaded_file.name,
                "mode": mode,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "params": {
                    "fps": fps,
                    "motion_threshold": motion_threshold,
                    "stable_duration": stable_duration,
                    "tag_sensitivity": tag_sensitivity,
                    "clahe": enable_clahe,
                    "threshold_path": enable_threshold,
                },
            },
        )
        st.success(f"Saved to {input_path}")
        success = False
        try:
            if mode == "Tag mode":
                success = _run_tag_pipeline(
                    input_path,
                    run_dir,
                    fps=fps,
                    motion_threshold=motion_threshold,
                    stable_duration=stable_duration,
                    tag_sensitivity=tag_sensitivity,
                    enable_clahe=enable_clahe,
                    enable_threshold=enable_threshold,
                )
            else:
                success = _run_marker_pipeline(input_path, run_dir, fps=fps, motion_threshold=motion_threshold)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Pipeline failed: {exc}")
        st.session_state["selected_run"] = str(run_dir)
        if success:
            st.success("Run completed. Open Review below.")
        else:
            st.warning("Run finished with warnings. Check logs above and reports below.")

if "selected_run" in st.session_state:
    selected_run = Path(st.session_state["selected_run"])
    if selected_run.exists():
        st.divider()
        st.subheader(f"Summary: {selected_run.name}")
        meta = load_run_metadata(selected_run)
        st.caption(
            f"Input: {meta.get('input_file', 'unknown')} • Mode: {meta.get('mode', 'n/a')} • Timestamp: {meta.get('timestamp', '')}"
        )
        artifacts = key_artifacts(selected_run)
        cols = st.columns(3)
        if artifacts.get("stable"):
            cols[0].image(str(artifacts["stable"]), caption="Stable frame", use_column_width=True)
        if artifacts.get("warped"):
            cols[1].image(str(artifacts["warped"]), caption="Warped board", use_column_width=True)
        if artifacts.get("tag_overlay"):
            cols[2].image(str(artifacts["tag_overlay"]), caption="Tag overlay", use_column_width=True)
        board_path = selected_run / "board_ids.json"
        if not board_path.exists():
            board_path = selected_run / "debug" / "board_ids.json"
        grid = load_board_grid(board_path)
        if grid:
            st.markdown("#### First board_ids grid")
            st.table(grid)
        report_paths = []
        for fname in ["TAG_CHECK.html", "CHECK.html"]:
            fpath = selected_run / fname
            if fpath.exists():
                report_paths.append(fpath)
        for report in report_paths:
            st.markdown(f"#### {report.name}")
            try:
                st.components.v1.html(report.read_text(encoding="utf-8", errors="ignore"), height=600, scrolling=True)
            except Exception:
                st.warning("Preview not available; open directly below.")
            st.markdown(f"[Open in new tab]({report.resolve().as_uri()})")
        st.link_button("Open Review page", href="/Review", type="primary")
    else:
        st.info("Select a previous run from the Review page or start a new one above.")
