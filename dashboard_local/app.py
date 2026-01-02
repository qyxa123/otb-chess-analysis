from pathlib import Path
from typing import Optional

import streamlit as st

from dashboard_local.utils import (
    create_run_dir,
    discover_runs,
    find_first_image,
    list_artifacts,
    load_run_metadata,
    parse_check_status,
    save_uploaded_file,
    stream_process,
    write_run_metadata,
)

st.set_page_config(page_title="OTBReview Local", layout="wide")


def run_pipeline(input_path: Path, outdir: Path, use_markers: bool) -> bool:
    st.write("### Running debug pipeline...")
    cmd = [
        "python",
        "scripts/run_debug_pipeline.py",
        "--input",
        str(input_path),
        "--outdir",
        str(outdir),
        "--use_markers",
        "1" if use_markers else "0",
    ]

    log_placeholder = st.empty()
    log_lines = []
    success = True

    process_stream = stream_process(cmd)
    for line in process_stream:
        log_lines.append(line)
        log_placeholder.code("\n".join(log_lines[-200:]), language="bash")
    if log_lines:
        log_placeholder.code("\n".join(log_lines[-200:]), language="bash")

    if getattr(process_stream, "returncode", 0) not in (0, None):
        success = False
    if log_lines and any("错误" in ln or "fail" in ln.lower() for ln in log_lines):
        success = False

    # Generate check report regardless of success
    st.write("### Generating CHECK.html report...")
    report_cmd = [
        "python",
        "scripts/make_check_report.py",
        "--outdir",
        str(outdir),
    ]
    report_stream = stream_process(report_cmd)
    for line in report_stream:
        log_lines.append(line)
        log_placeholder.code("\n".join(log_lines[-200:]), language="bash")
    if getattr(report_stream, "returncode", 0) not in (0, None):
        success = False

    return success


def display_images(run_dir: Path):
    debug_dir = run_dir / "debug"
    col1, col2 = st.columns(2)

    grid_overlay = debug_dir / "grid_overlay.png"
    if grid_overlay.exists():
        col1.image(str(grid_overlay), caption="grid_overlay.png", use_column_width=True)
    else:
        col1.info("grid_overlay.png not found")

    aruco_preview = debug_dir / "aruco_preview.png"
    if aruco_preview.exists():
        col2.image(str(aruco_preview), caption="aruco_preview.png", use_column_width=True)
    else:
        col2.info("aruco_preview.png not found")

    col3, col4 = st.columns(2)
    warped = find_first_image(debug_dir / "warped_boards")
    if warped:
        col3.image(str(warped), caption=f"warped_boards/{warped.name}", use_column_width=True)
    else:
        col3.info("No warped board images found")

    stable = find_first_image(debug_dir / "stable_frames")
    if stable:
        col4.image(str(stable), caption=f"stable_frames/{stable.name}", use_column_width=True)
    else:
        col4.info("No stable frames found")


def render_check_html(run_dir: Path):
    check_path = run_dir / "CHECK.html"
    if not check_path.exists():
        st.warning("CHECK.html not found. Try rerunning the report generator.")
        return
    html_content = check_path.read_text(encoding="utf-8", errors="ignore")
    st.components.v1.html(html_content, height=800, scrolling=True)
    st.markdown(f"[Open in browser]({check_path.resolve().as_uri()})")


def artifact_browser(run_dir: Path):
    st.write("### Artifacts")
    artifacts = list_artifacts(run_dir)
    if not artifacts:
        st.info("No artifacts found yet.")
        return
    for rel, path in artifacts:
        with st.expander(rel, expanded=False):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                st.image(str(path), caption=rel, use_column_width=True)
            elif path.suffix.lower() in {".json", ".txt", ".csv", ".pgn"}:
                try:
                    st.code(path.read_text(encoding="utf-8", errors="ignore")[:4000])
                except Exception:
                    st.info("Preview unavailable")
            with open(path, "rb") as f:
                st.download_button(
                    label="Download",
                    data=f,
                    file_name=path.name,
                    mime="application/octet-stream",
                    key=f"download-{rel}",
                )


def home_tab():
    st.title("OTBReview Local")
    st.markdown(
        """
        **Quick Start (3 steps)**
        1. Install dependencies (see README) and start this dashboard.
        2. Upload your chess video (.mp4/.mov/.mkv).
        3. Click **Run Debug Pipeline** then view the generated report.
        """
    )


def upload_and_run_tab():
    st.header("Upload & Run")
    uploaded_file = st.file_uploader("Upload video", type=["mp4", "mov", "mkv", "MP4", "MOV", "MKV"])

    mode = st.radio(
        "Mode",
        options=["Marker mode (ArUco corners)", "Tag mode (piece tags + corners)"],
        help="Marker mode uses ArUco corner markers (0/1/2/3). Tag mode expects piece tags plus corners.",
    )
    # Both modes rely on the corner markers for warp; Tag mode simply assumes piece tags are also present.
    use_markers = True

    run_button = st.button("Run Debug Pipeline", type="primary", use_container_width=True)
    if run_button:
        if uploaded_file is None:
            st.error("Please upload a video file first.")
            return
        run_dir, run_id = create_run_dir()
        input_path = save_uploaded_file(uploaded_file, run_dir)
        write_run_metadata(
            run_dir,
            {
                "run_id": run_id,
                "input_file": uploaded_file.name,
                "mode": mode,
            },
        )

        st.success(f"Saved upload to {input_path}")
        success = run_pipeline(input_path=input_path, outdir=run_dir, use_markers=use_markers)
        if success:
            st.success("Pipeline completed. See Results tab.")
        else:
            st.warning("Pipeline finished with warnings or errors. Check logs and artifacts.")
        st.session_state["selected_run"] = run_dir


def results_tab():
    st.header("Results")
    runs = discover_runs()
    if not runs:
        st.info("No runs yet. Upload a video in the Upload & Run tab.")
        return

    default_run = st.session_state.get("selected_run")
    options = {f"{run_id}": path for run_id, path in runs}
    default_key: Optional[str] = None
    if default_run:
        for run_id, path in runs:
            if path == default_run:
                default_key = run_id
                break
    labels = list(options.keys())
    index = 0
    if default_key in labels:
        index = labels.index(default_key)
    selected_label = st.selectbox("Select run", labels, index=index)
    run_dir = options[selected_label]
    st.session_state["selected_run"] = run_dir

    meta = load_run_metadata(run_dir)
    st.write(
        f"**Run ID:** {selected_label}  |  **Input:** {meta.get('input_file', 'unknown')}  |  **Mode:** {meta.get('mode', 'n/a')}"
    )

    display_images(run_dir)
    render_check_html(run_dir)
    artifact_browser(run_dir)


def history_tab():
    st.header("History")
    runs = discover_runs()
    if not runs:
        st.info("No history yet. Runs will appear here after you process a video.")
        return

    for run_id, path in runs:
        meta = load_run_metadata(path)
        check_status = parse_check_status(path / "CHECK.html") or "Unknown"
        with st.expander(f"{run_id} | {meta.get('input_file', 'unknown')} | Status: {check_status}"):
            st.write(f"Mode: {meta.get('mode', 'n/a')}")
            st.button(
                "Open in Results",
                key=f"open-{run_id}",
                on_click=lambda p=path: st.session_state.update({"selected_run": p, "active_tab": "Results"}),
            )


def main():
    tab_names = ["Home", "Upload & Run", "Results", "History"]
    active_tab = st.session_state.get("active_tab", tab_names[0])
    tabs = st.tabs(tab_names)

    with tabs[0]:
        home_tab()
        st.session_state["active_tab"] = "Home"
    with tabs[1]:
        upload_and_run_tab()
        st.session_state["active_tab"] = "Upload & Run"
    with tabs[2]:
        results_tab()
        st.session_state["active_tab"] = "Results"
    with tabs[3]:
        history_tab()
        st.session_state["active_tab"] = "History"


if __name__ == "__main__":
    main()
