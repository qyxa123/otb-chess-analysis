from __future__ import annotations

import shutil
from pathlib import Path

import streamlit as st

from dashboard.utils import BASE_OUTDIR, key_artifacts, load_json, run_history, zip_run_directory

st.title("Review")
st.caption("Replay the game, inspect evaluations, and download artifacts.")

history = run_history()
if not history:
    st.info("No runs yet. Go to Home / New Analysis to start.")
    st.stop()

run_ids = [item["run_id"] for item in history]
run_lookup = {item["run_id"]: item for item in history}

selected_id = st.selectbox(
    "Select run",
    run_ids,
    index=run_ids.index(Path(st.session_state.get("selected_run", "")).name) if Path(st.session_state.get("selected_run", "")).name in run_ids else 0,
    format_func=lambda x: f"{x} — {run_lookup[x].get('input_file','')}" if x in run_lookup else x,
)

if selected_id:
    run_dir = BASE_OUTDIR / selected_id
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
        if isinstance(analysis_json, dict) and analysis_json:
            metadata = analysis_json.get("metadata", {})
            warnings = list(metadata.get("warnings", []))
            if metadata.get("engine_warning"):
                warnings.append(metadata["engine_warning"])
            for warning in dict.fromkeys(warnings):
                st.warning(warning)
            if metadata.get("partial"):
                st.warning("Recognition stopped at an uncertain observation. Only the reliable prefix is available.")
            evaluated = [move for move in analysis_json.get("moves", []) if move.get("move_number", 0) > 0]
            if evaluated:
                source = metadata.get("analysis_source") or evaluated[0].get("analysis_source", "stockfish")
                st.markdown("### Material evaluation (no engine)" if source == "material" else "### Stockfish evaluation")
                st.metric("Key moves", len(analysis_json.get("keyMoves", [])))
                graph = [{"ply": move["move_number"], "evaluation (pawns)": move.get("eval_cp", 0) / 100}
                         for move in evaluated if move.get("eval_cp") is not None]
                if graph:
                    st.line_chart({"White advantage (pawns)": [row["evaluation (pawns)"] for row in graph]})
            elif not warnings:
                st.info("Replay is available without engine evaluations.")
        moves_json = load_json(run_dir / "moves.json")
        if moves_json:
            st.markdown("### Moves")
            for idx, mv in enumerate(moves_json, start=1):
                san = mv.get("san", "?") if isinstance(mv, dict) else str(mv)
                st.write(f"{(idx + 1) // 2}{'.' if idx % 2 else '...'} {san}")

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
                st.download_button(f"Download {fname}", fpath.read_bytes(), file_name=fname)
else:
    st.info("Upload and run an analysis first.")
