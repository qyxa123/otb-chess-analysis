from __future__ import annotations

import shutil
from pathlib import Path

import streamlit as st

from dashboard.utils import key_artifacts, load_json, run_history, zip_run_directory

st.title("Review")
st.caption("Replay the game, check accuracy, and download artifacts.")

history = run_history()
if not history:
    st.info("No runs yet. Go to Home / New Analysis to start.")
    st.stop()

run_ids = [item["run_id"] for item in history]
run_lookup = {item["run_id"]: item for item in history}

selected_id = st.selectbox(
    "Select run",
    run_ids,
    format_func=lambda x: f"{x} — {run_lookup[x].get('input_file','')}" if x in run_lookup else x,
)

if selected_id:
    run_dir = Path("out/runs") / selected_id
    if not run_dir.exists():
        st.error("Run folder missing.")
    else:
        meta = load_json(run_dir / "run_meta.json")
        st.subheader(meta.get("input_file", selected_id))
        st.caption(f"Mode: {meta.get('mode','n/a')} • Timestamp: {meta.get('timestamp','')}")

        artifacts = key_artifacts(run_dir)
        cols = st.columns(3)
        if artifacts.get("stable"):
            cols[0].image(str(artifacts["stable"]), caption="Stable frame", use_column_width=True)
        if artifacts.get("warped"):
            cols[1].image(str(artifacts["warped"]), caption="Warped board", use_column_width=True)
        if artifacts.get("tag_overlay"):
            cols[2].image(str(artifacts["tag_overlay"]), caption="Tag overlay", use_column_width=True)

        index_html = run_dir / "index.html"
        if index_html.exists():
            st.markdown("### Web Review")
            st.components.v1.html(index_html.read_text(encoding="utf-8", errors="ignore"), height=700, scrolling=True)
        else:
            st.info("index.html not found. Generate it by running the full analysis script.")

        analysis_json = load_json(run_dir / "analysis.json")
        if analysis_json:
            st.markdown("### Accuracy summary")
            cols = st.columns(3)
            cols[0].metric("White accuracy", f"{analysis_json.get('white_accuracy','--')}%")
            cols[1].metric("Black accuracy", f"{analysis_json.get('black_accuracy','--')}%")
            cols[2].metric("Key moves", len(analysis_json.get("key_moves", [])))
            if analysis_json.get("advantage_graph"):
                st.line_chart(analysis_json.get("advantage_graph"))
        moves_json = load_json(run_dir / "moves.json")
        if moves_json:
            st.markdown("### Moves")
            for idx, mv in enumerate(moves_json, start=1):
                st.write(f"{idx}. {mv}")

        st.markdown("### Downloads")
        pgn_path = run_dir / "game.pgn"
        if pgn_path.exists():
            st.download_button("Download PGN", data=pgn_path.read_bytes(), file_name=pgn_path.name)
        analysis_path = run_dir / "analysis.json"
        if analysis_path.exists():
            st.download_button("Download analysis.json", data=analysis_path.read_bytes(), file_name=analysis_path.name)
        st.download_button(
            "Download full ZIP",
            data=zip_run_directory(run_dir),
            file_name=f"{run_dir.name}.zip",
            mime="application/zip",
        )

        st.markdown("### Reports")
        for fname in ["TAG_CHECK.html", "CHECK.html"]:
            fpath = run_dir / fname
            if fpath.exists():
                st.markdown(f"#### {fname}")
                st.components.v1.html(fpath.read_text(encoding="utf-8", errors="ignore"), height=500, scrolling=True)
                st.markdown(f"[Open in new tab]({fpath.resolve().as_uri()})")
else:
    st.info("Upload and run an analysis first.")
