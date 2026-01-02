from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from dashboard_local.utils import (
    create_run_dir,
    discover_runs,
    gather_tag_overlays,
    key_artifacts,
    load_board_ids,
    load_run_metadata,
    parse_pgn_advantage,
    run_status,
    save_uploaded_file,
    stream_process,
    write_run_metadata,
    zip_run_directory,
)


st.set_page_config(page_title="OTBReview Local Dashboard", layout="wide")


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


def run_marker_pipeline(
    input_path: Path,
    run_dir: Path,
    fps: float,
    stability: float,
) -> bool:
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


def run_tag_pipeline(
    input_path: Path,
    run_dir: Path,
    fps: float,
    stability: float,
    sensitivity: float,
) -> bool:
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
        "--motion-threshold",
        str(stability),
    ]
    if sensitivity != 1.0:
        cmd.extend(["--tag-sensitivity", str(sensitivity)])
    code, logs = _stream_logs(cmd)
    return code == 0 and "fail" not in logs.lower()


def sidebar_history():
    st.sidebar.title("History")
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
    selected = st.sidebar.radio("Select a run", labels, index=0 if labels else None)
    st.sidebar.markdown("---")
    return mapping.get(selected)


def _render_board_table(board_ids):
    df = pd.DataFrame(board_ids, columns=["A", "B", "C", "D", "E", "F", "G", "H"])
    df.index = [f"{8 - i}" for i in range(8)]
    st.dataframe(df, use_container_width=True)


def _render_reports(run_dir: Path):
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


def _render_downloads(run_dir: Path):
    st.markdown("### Downloads")
    zip_bytes = zip_run_directory(run_dir)
    st.download_button("Download full ZIP", data=zip_bytes, file_name=f"{run_dir.name}.zip")
    for fname in ["game.pgn", "moves.json", "board_ids.json", "debug/board_ids.json", "debug/tag_metrics.csv"]:
        fpath = run_dir / fname
        if fpath.exists():
            with open(fpath, "rb") as f:
                st.download_button(f"Download {fname}", data=f, file_name=fpath.name, key=f"dl-{fname}-{run_dir.name}")


def _render_results(run_dir: Path):
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

    debug_dir = run_dir / "debug"
    overlays = gather_tag_overlays(debug_dir)
    if overlays:
        st.markdown("#### Tag overlays")
        st.image([str(p) for p in overlays[:6]], caption=[p.name for p in overlays[:6]], use_column_width=True)

    board_ids = load_board_ids(run_dir)
    if board_ids:
        st.markdown("#### 8x8 Detected IDs")
        _render_board_table(board_ids[0] if isinstance(board_ids[0], list) and isinstance(board_ids[0][0], list) else board_ids)

    _render_reports(run_dir)
    _render_downloads(run_dir)


def _render_review_panel(run_dir: Path):
    st.markdown("### Chess.com-style Review")
    pgn_path = run_dir / "game.pgn"
    if not pgn_path.exists():
        st.info("No PGN yet. Run Tag mode to decode moves.")
        return

    review = parse_pgn_advantage(pgn_path)
    if not review:
        st.warning("Unable to parse PGN")
        return

    col1, col2 = st.columns(2)
    col1.metric("Accuracy (White)", f"{review['accuracy']['white']}%")
    col2.metric("Accuracy (Black)", f"{review['accuracy']['black']}%")

    st.markdown("#### Advantage Graph")
    st.line_chart(review["evals"], height=200)

    counts = review.get("label_counts", {})
    summary_df = pd.DataFrame([
        {"Label": k, "Count": v} for k, v in counts.items()
    ])
    st.bar_chart(summary_df.set_index("Label"))

    st.markdown("#### Key Moves + Coach")
    from game_review import GameReviewFormatter

    formatter = GameReviewFormatter()
    swing_list = []
    evals = review["evals"]
    for idx, move in enumerate(review["moves"]):
        eval_before = evals[idx - 1] if idx > 0 else 0
        eval_after = evals[idx]
        swing = eval_after - eval_before
        label = formatter.label_move(swing if idx % 2 == 0 else -swing)
        swing_list.append((abs(swing), idx, move, label))
    swing_list.sort(reverse=True)

    for swing, idx, move, label in swing_list[:5]:
        coach = formatter.coach_text(label, move, None, swing if idx % 2 == 0 else -swing)
        with st.expander(f"Move {idx + 1}: {move} • {label}"):
            st.write(coach.headline)
            st.write(coach.detail)
            st.write("Suggestions:")
            for s in coach.suggestions:
                st.write(f"- {s}")
            st.caption("Retry: imagine an alternative move and compare swing in your head — higher swing means risk.")


def upload_and_run(selected_run: Optional[Path]):
    st.header("Upload & Run")
    uploaded_file = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "MP4", "MOV", "MKV"])
    mode = st.radio("Mode", ["Marker Mode", "Tag Mode"], help="Marker = corner ArUco only; Tag = chess piece tags")
    fps = st.slider("FPS sampling", 1.0, 12.0, 3.0, 0.5)
    stability = st.slider("Stability threshold (motion)", 0.001, 0.05, 0.01, 0.001)
    sensitivity = st.slider("Tag detection sensitivity", 0.5, 1.5, 1.0, 0.1)

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
                "fps": fps,
                "stability": stability,
                "sensitivity": sensitivity,
            },
        )
        st.success(f"Saved upload to {input_path}")
        success = False
        if "Tag" in mode:
            success = run_tag_pipeline(input_path, run_dir, fps, stability, sensitivity)
        else:
            success = run_marker_pipeline(input_path, run_dir, fps, stability)

        st.session_state["selected_run"] = run_dir
        if success:
            st.success("Pipeline completed!")
        else:
            st.warning("Pipeline finished with warnings. Check logs and reports.")


def main():
    st.title("OTBReview Local Dashboard")
    selected_from_sidebar = sidebar_history()
    tabs = st.tabs(["Upload & Run", "Results / Replay", "History"])
    with tabs[0]:
        upload_and_run(selected_from_sidebar)
    with tabs[1]:
        run_dir: Optional[Path] = st.session_state.get("selected_run") or selected_from_sidebar
        if run_dir and Path(run_dir).exists():
            _render_results(Path(run_dir))
            _render_review_panel(Path(run_dir))
        else:
            st.info("Select or create a run to view results")
    with tabs[2]:
        st.markdown("### Previous runs")
        runs = discover_runs()
        for run_id, path in runs:
            meta = load_run_metadata(path)
            status = run_status(path)
            cols = st.columns([2, 2, 1, 1])
            cols[0].write(run_id)
            cols[1].caption(f"{meta.get('input_file', 'video')} • {meta.get('timestamp', '')}")
            cols[2].write(status)
            if cols[3].button("Open", key=f"open-{run_id}"):
                st.session_state["selected_run"] = path
                st.experimental_rerun()


if __name__ == "__main__":
    main()
