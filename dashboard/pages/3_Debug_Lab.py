from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from dashboard.utils import (
    key_artifacts,
    list_images,
    load_board_sequences,
    load_csv,
    load_json,
    run_history,
)
from otbreview.pipeline.board_detect import detect_and_warp_board_debug
from otbreview.pipeline.pieces import detect_pieces_tags

st.title("Debug Lab")
st.caption("Developer corner: inspect CV outputs, rerun small pieces, and read diagnostics.")

history = run_history()
run_ids = [item["run_id"] for item in history]
if not run_ids:
    st.info("No runs yet. Run an analysis first.")
    st.stop()

selected_id = st.selectbox("Select run", run_ids)
run_dir = Path("out/runs") / selected_id

debug_dir = run_dir / "debug"
st.divider()
st.subheader("Quick gallery")
artifacts = key_artifacts(run_dir)
cols = st.columns(4)
if artifacts.get("stable"):
    cols[0].image(str(artifacts["stable"]), caption="Stable frame")
if artifacts.get("warped"):
    cols[1].image(str(artifacts["warped"]), caption="Warped")
if artifacts.get("grid"):
    cols[2].image(str(artifacts["grid"]), caption="Grid overlay")
if artifacts.get("tag_overlay"):
    cols[3].image(str(artifacts["tag_overlay"]), caption="Tag overlay")

st.markdown("### Stable frames")
st.image([str(p) for p in list_images(debug_dir / "stable_frames")[:12]], width=140)

st.markdown("### Tag overlays (first five)")
st.image([str(p) for p in list_images(debug_dir / "tag_overlays")[:5]], width=180)

metrics = load_csv(debug_dir / "tag_metrics.csv")
if not metrics.empty:
    st.markdown("### tag_metrics.csv")
    st.dataframe(metrics)
    auto_diag = []
    first_corner = int(metrics.iloc[0]["corners_detected"]) if "corners_detected" in metrics.columns else 0
    first_unique = int(metrics.iloc[0]["num_unique_ids"]) if "num_unique_ids" in metrics.columns else 0
    if first_corner < 4:
        auto_diag.append("Corners <4 — camera may crop markers; keep 0/1/2/3 fully visible.")
    if first_unique < 28:
        auto_diag.append("Unique tags below 28 — camera too high, tags too small, or focus/glare issues.")
    if "confidence_flag" in metrics.columns and (metrics["confidence_flag"] == "DUPLICATE_IDS").any():
        auto_diag.append("Duplicate IDs detected; reprint stickers to remove duplicates/reflections.")
    if auto_diag:
        st.warning("\n".join(auto_diag))

st.markdown("### Board IDs table (select frame)")
board_seq = load_board_sequences(run_dir / "board_ids.json")
if not board_seq:
    board_seq = load_board_sequences(debug_dir / "board_ids.json")
if board_seq:
    frame_idx = st.slider("Frame index", 0, len(board_seq) - 1, 0)
    st.table(board_seq[frame_idx])
else:
    st.info("board_ids.json missing. Run tag mode first.")

st.divider()
st.subheader("Frame-level rerun")
with st.form("rerun_form"):
    stable_frame = st.selectbox("Pick stable frame", list_images(debug_dir / "stable_frames"))
    rerun_tag = st.checkbox("Rerun tag detection (requires warped board)", value=True)
    sensitivity = st.slider("Tag min-area multiplier", 0.2, 2.0, 1.0, 0.1)
    submit = st.form_submit_button("Run rerun")

if submit and stable_frame:
    stable_path = Path(stable_frame)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        success, warped, preview, grid = detect_and_warp_board_debug(
            frame_path=str(stable_path), use_markers=True, output_dir=str(tmpdir_path), frame_idx=0
        )
        if warped is not None:
            st.image(warped, caption="Warped rerun", use_column_width=True)
        if rerun_tag and warped is not None:
            state = detect_pieces_tags(
                warped,
                0,
                str(tmpdir_path),
                tag_family="aruco5x5_100",
                min_area_ratio=0.0005 * sensitivity,
            )
            st.image(str(tmpdir_path / "overlay_0001.png"), caption="Tag overlay (rerun)")
            st.json({"unique_ids": len({pid for row in state['piece_ids'] for pid in row if pid}), "warnings": state.get("tag_warnings", [])})

st.divider()
st.subheader("Diagnosis")
report = load_json(run_dir / "run_meta.json")
report_lines = []
if report.get("mode") == "Tag mode" and metrics is not None and not metrics.empty:
    first = metrics.iloc[0]
    if first.get("corners_detected", 0) < 4:
        report_lines.append("Corners missing — raise camera, avoid occlusion, keep board flat.")
    if first.get("num_unique_ids", 0) < 20:
        report_lines.append("Very low tag count — try 5mm tags, ensure focus, reduce glare.")
if report_lines:
    st.write("\n".join(report_lines))
else:
    st.info("No additional warnings.")
