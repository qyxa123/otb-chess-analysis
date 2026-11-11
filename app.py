import streamlit as st
import os
import sys
import shutil
import time
import json
from pathlib import Path
from datetime import datetime
import contextlib
import io
from typing import Dict, List, Tuple

import altair as alt
import pandas as pd
import chess
import chess.pgn
import chess.svg
import zipfile

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from otbreview.pipeline.main import analyze_video
from self_analysis import analyze_pgn
from game_review import GameReviewFormatter

# Config
RUNS_DIR = PROJECT_ROOT / "runs"
RUNS_DIR.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Chess Video Analysis",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State ---
if 'run_id' not in st.session_state:
    st.session_state.run_id = None
if 'page' not in st.session_state:
    st.session_state.page = "home"

# --- Sidebar: History ---
st.sidebar.title("History")
runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True)

if st.sidebar.button("🏠 New Analysis"):
    st.session_state.run_id = None
    st.session_state.page = "home"
    st.rerun()

st.sidebar.markdown("---")
for run_dir in runs:
    run_name = run_dir.name
    # Try to read meta for better name?
    label = run_name
    if st.sidebar.button(f"📄 {label}", key=f"hist_{run_name}"):
        st.session_state.run_id = run_name
        st.session_state.page = "results"
        st.rerun()

# --- Functions ---


def _load_pgn_text(run_dir: Path) -> str:
    pgn_path = run_dir / "game.pgn"
    if not pgn_path.exists():
        raise FileNotFoundError("No PGN generated for this run.")
    return pgn_path.read_text(encoding="utf-8")


def _board_at_ply(pgn_text: str, ply: int) -> Tuple[chess.Board, List[chess.Move]]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Invalid PGN provided")
    if game.errors:
        raise ValueError(f"Invalid PGN: {game.errors[0]}")
    board = game.board()
    moves = list(game.mainline_moves())
    for mv in moves[:ply]:
        board.push(mv)
    return board, moves


def _build_review_payload(run_dir: Path) -> Dict[str, object]:
    pgn_text = _load_pgn_text(run_dir)
    analysis_path = run_dir / "move_analysis.json"
    if analysis_path.exists():
        analysis: List[Dict[str, object]] = json.loads(analysis_path.read_text())
    else:
        analysis = analyze_pgn(pgn_text)
        analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    reviewer = GameReviewFormatter()
    game_review = reviewer.build_review(pgn_text, analysis)

    # Evaluation graph
    evaluation_scores = [
        {"ply": idx + 1, "evaluation": float(item.get("eval_after", 0.0))}
        for idx, item in enumerate(analysis)
    ]
    (run_dir / "evaluation_scores.json").write_text(
        json.dumps(evaluation_scores, indent=2), encoding="utf-8"
    )

    # Key moves and follow-up suggestions
    key_labels = {"Brilliant", "Great", "Mistake", "Blunder", "Miss"}
    key_moves = []
    follow_ups = []
    for idx, review in enumerate(game_review.reviews):
        if review.label not in key_labels:
            continue
        candidates = analysis[idx].get("candidate_lines", [])
        follow_up_options = [
            {
                "san": cand.get("san"),
                "eval_after": cand.get("eval_after"),
                "continuation": cand.get("continuation"),
            }
            for cand in candidates
        ]
        follow_ups.append(
            {
                "ply": review.ply,
                "move": review.san,
                "label": review.label,
                "options": follow_up_options,
            }
        )
        key_moves.append(
            {
                "ply": review.ply,
                "san": review.san,
                "label": review.label,
                "eval_before": review.eval_before,
                "eval_after": review.eval_after,
                "perspective_change": review.perspective_change,
                "best_san": review.best_san,
                "coach": {
                    "headline": review.coach.headline,
                    "detail": review.coach.detail,
                    "suggestions": review.coach.suggestions,
                },
                "arrow": analysis[idx].get("suggestion_arrow"),
                "follow_up": follow_up_options,
            }
        )

    (run_dir / "key_moves.json").write_text(json.dumps(key_moves, indent=2), encoding="utf-8")
    (run_dir / "follow_up_moves.json").write_text(json.dumps(follow_ups, indent=2), encoding="utf-8")

    classification_counts: Dict[str, int] = {}
    for review in game_review.reviews:
        classification_counts[review.label] = classification_counts.get(review.label, 0) + 1

    annotated_path = run_dir / "annotated_game.pgn"
    annotated_path.write_text(game_review.annotated_pgn, encoding="utf-8")

    return {
        "pgn_text": pgn_text,
        "game_review": game_review,
        "evaluation_scores": evaluation_scores,
        "classification_counts": classification_counts,
        "key_moves": key_moves,
        "follow_ups": follow_ups,
    }


def run_analysis(video_file, params):
    # Create Run ID
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Save Video
    video_path = run_dir / ("input_video" + Path(video_file.name).suffix.lower())
    with open(video_path, "wb") as f:
        f.write(video_file.getbuffer())
    
    # Save Params
    with open(run_dir / "meta.json", "w") as f:
        json.dump(params, f, indent=2)
        
    # Run Pipeline
    log_capture_string = io.StringIO()
    
    status_container = st.status("Processing video...", expanded=True)
    log_area = status_container.empty()
    
    # Custom stdout to capture logs and update UI
    class StreamlitSink:
        def write(self, message):
            log_capture_string.write(message)
            sys.__stdout__.write(message)
            # Update UI occasionally? (Can be slow)
            # log_area.code(log_capture_string.getvalue()[-1000:]) 
        def flush(self):
            sys.__stdout__.flush()

    # We use a simple redirect for now, updating UI after steps might be hard without callbacks
    # Instead, we'll just run it and show the log at the end or if it fails
    
    try:
        with contextlib.redirect_stdout(StreamlitSink()), contextlib.redirect_stderr(StreamlitSink()):
            analyze_video(
                video_path=str(video_path),
                outdir=str(run_dir),
                use_markers=params['use_markers'],
                use_piece_tags=params.get('use_piece_tags', True),
                motion_threshold=params['motion_threshold'],
                stable_duration=params['stable_duration']
            )
        (run_dir / "logs.txt").write_text(log_capture_string.getvalue(), encoding="utf-8")
        status_container.update(label="Analysis Complete!", state="complete", expanded=False)
        st.session_state.run_id = run_id
        st.session_state.page = "results"
        st.rerun()
        
    except Exception as e:
        status_container.update(label="Analysis Failed!", state="error", expanded=True)
        st.error(f"Error during analysis: {str(e)}")
        st.text_area("Logs", log_capture_string.getvalue(), height=300)
        # Save logs even on failure
        with open(run_dir / "logs.txt", "w") as f:
            f.write(log_capture_string.getvalue())
        return

    # Save logs
    with open(run_dir / "logs.txt", "w") as f:
        f.write(log_capture_string.getvalue())


def _render_board(board: chess.Board, arrow: Dict[str, str] = None):
    arrows = []
    if arrow:
        try:
            arrows.append(
                chess.svg.Arrow(
                    chess.parse_square(arrow["from"]),
                    chess.parse_square(arrow["to"]),
                    color="#ff4136",
                )
            )
        except Exception:
            pass
    svg = chess.svg.board(board=board, arrows=arrows, size=380)
    st.components.v1.html(svg, height=400)


def _render_game_review_tab(run_dir: Path):
    try:
        payload = _build_review_payload(run_dir)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Unable to build game review: {exc}")
        return

    game_review = payload["game_review"]

    st.markdown("### Game Review")
    st.info("This tab uses a simple material heuristic. Scores and suggestions are approximate. "
            "For the pipeline's Stockfish analysis, open Debug → Replay.")
    st.metric("Half-moves", len(game_review.reviews))

    chart_df = pd.DataFrame(payload["evaluation_scores"], columns=["ply", "evaluation"])
    chart_df["move"] = chart_df["ply"]
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(x="move", y="evaluation", tooltip=["move", "evaluation"])
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.markdown("### Key Moves & Coach")
    key_moves = payload["key_moves"]
    if not key_moves:
        st.info("No key moves identified for this game.")
        st.download_button("Download PGN", payload["pgn_text"], file_name=f"{run_dir.name}.pgn",
                           key="review_pgn_no_key_moves")
        return

    state_key = f"key_move_index_{run_dir.name}"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    current_idx = st.session_state[state_key]
    current_idx = max(0, min(current_idx, len(key_moves) - 1))
    st.session_state[state_key] = current_idx
    current_move = key_moves[current_idx]

    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
    with nav_col1:
        if st.button("⬅️ Previous", disabled=current_idx == 0):
            st.session_state[state_key] = current_idx - 1
            st.rerun()
    with nav_col2:
        st.markdown(
            f"**Move {current_move['ply']}: {current_move['san']} ({current_move['label']})**"
        )
    with nav_col3:
        if st.button("Next Move ➡️", disabled=current_idx >= len(key_moves) - 1):
            st.session_state[state_key] = current_idx + 1
            st.rerun()

    board, moves = _board_at_ply(payload["pgn_text"], current_move["ply"] - 1)
    display_col, coach_col = st.columns([1, 1])

    with display_col:
        _render_board(board, current_move.get("arrow"))
        st.caption("Position before the key move. Arrows highlight the engine suggestion.")

        st.markdown("**Follow-Up Variations**")
        follow_options = current_move.get("follow_up", [])
        if follow_options:
            option_labels = [f"{opt['san']} (eval {opt['eval_after']:.1f})" for opt in follow_options]
            selected = st.selectbox("Show Follow-Up", option_labels, key=f"follow_{state_key}_{current_idx}")
            selected_idx = option_labels.index(selected)
            st.write(f"Continuation: {follow_options[selected_idx]['continuation']}")
        else:
            st.info("No follow-up variations available for this move.")

        with st.expander("Retry this move"):
            legal_sans = [board.san(mv) for mv in board.legal_moves]
            choice = st.selectbox("Pick your move", legal_sans, key=f"retry_{state_key}_{current_idx}")
            if st.button("Submit retry", key=f"retry_btn_{state_key}_{current_idx}"):
                target = current_move.get("best_san") or current_move["san"]
                if choice == target:
                    st.success("Correct move! Your positional score is now +5.")
                else:
                    st.error(
                        f"Not quite. {target} keeps the advantage. {current_move['coach']['detail']}"
                    )
                best_arrow = current_move.get("arrow")
                if best_arrow:
                    st.caption("Correct move highlighted below:")
                    _render_board(board, best_arrow)

    with coach_col:
        st.markdown(f"#### Coach says: {current_move['coach']['headline']}")
        st.write(current_move["coach"]["detail"])
        st.markdown("**Suggestions**")
        for tip in current_move["coach"].get("suggestions", []):
            st.markdown(f"- {tip}")

    st.markdown("### Full PGN & Downloads")
    st.text_area("Game PGN", payload["pgn_text"], height=180)
    dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)
    with dl_col1:
        st.download_button("Download PGN", payload["pgn_text"], file_name=f"{run_dir.name}.pgn", key="review_pgn")
    with dl_col2:
        st.download_button(
            "Analysis JSON",
            data=json.dumps(payload["key_moves"], indent=2),
            file_name="key_moves.json",
        )
    with dl_col3:
        st.download_button(
            "Evaluation Scores",
            data=json.dumps(payload["evaluation_scores"], indent=2),
            file_name="evaluation_scores.json",
        )
    with dl_col4:
        st.download_button(
            "Follow-Up Moves",
            data=json.dumps(payload["follow_ups"], indent=2),
            file_name="follow_up_moves.json",
        )


def show_results(run_id):
    run_dir = RUNS_DIR / run_id
    st.title(f"Results: {run_id}")

    if not run_dir.exists():
        st.error("Run directory not found.")
        return

    analysis_path = run_dir / "analysis.json"
    if analysis_path.exists():
        metadata = json.loads(analysis_path.read_text(encoding="utf-8")).get("metadata", {})
        if metadata.get("partial"):
            st.warning("Recognition stopped at an uncertain observation. PGN contains only the reliable prefix.")
        for warning in metadata.get("warnings", []):
            st.warning(warning)

    page_tabs = st.tabs(["Overview", "Game Review", "Debug"])

    with page_tabs[0]:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📝 PGN")
            pgn_path = run_dir / "game.pgn"
            if pgn_path.exists():
                pgn_text = pgn_path.read_text()
                st.text_area("PGN", pgn_text, height=200)
                st.download_button("Download PGN", pgn_text, file_name=f"{run_id}.pgn")
            else:
                st.warning("No PGN generated.")

        with col2:
            st.subheader("📊 Files")
            # Zip download
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                for artifact in sorted(run_dir.rglob("*")):
                    if artifact.is_file() and artifact.suffix.lower() not in {".zip", ".mp4", ".mov", ".avi", ".mkv"}:
                        zf.write(artifact, artifact.relative_to(run_dir))
            st.download_button("Download Full Report (ZIP)", archive.getvalue(), file_name=f"{run_id}_export.zip")

    with page_tabs[1]:
        _render_game_review_tab(run_dir)

    with page_tabs[2]:
        # Debug Images
        st.subheader("🔍 Debug Visualization")
        debug_dir = run_dir / "debug"

        tabs = st.tabs(["Stable Frames", "Warped Board", "Grid Overlay", "Occupancy", "Replay"])

        with tabs[0]:
            stable_dir = debug_dir / "stable_frames"
            if stable_dir.exists():
                images = sorted(list(stable_dir.glob("*.png")) + list(stable_dir.glob("*.jpg")))
                if images:
                    st.image(str(images[0]), caption="First Stable Frame", use_container_width=True)
                    if len(images) > 1:
                        st.info(f"Total stable frames: {len(images)}")
                else:
                    st.write("No stable frames found.")

        with tabs[1]:
            # Warped board debug
            warped_debug = debug_dir / "warped_board_debug.png"
            if warped_debug.exists():
                 st.image(str(warped_debug), caption="Warped Board (Check Perspective)", use_container_width=True)
            else:
                 st.write("No warped board debug image.")

        with tabs[2]:
            grid_overlay = debug_dir / "grid_overlay.png"
            if grid_overlay.exists():
                 st.image(str(grid_overlay), caption="Grid Overlay (Check Alignment)", use_container_width=True)
            else:
                 st.write("No grid overlay image.")

        with tabs[3]:
            # Occupancy / Cells
            # Maybe show a grid of recognized cells for the first frame?
            # Or just link to the folder
            st.write("Cell images are saved in debug/cells/")

        with tabs[4]:
            st.subheader("♟️ Web Replay")
            # Check if index.html exists
            index_html = run_dir / "index.html"
            if index_html.exists():
                html_content = index_html.read_text(encoding='utf-8')
                st.components.v1.html(html_content, height=800, scrolling=True)
            else:
                st.warning("Web replay file (index.html) not found.")


# --- Main Logic ---

if st.session_state.page == "home":
    st.title("♟️ OTB Chess Video Analysis")
    st.markdown("""
    Turn your over-the-board chess videos into PGNs automatically!
    
    **Instructions:**
    1. Record from the starting position, with a8 at the top left. Keep the full board visible.
       The default mode requires ArUco 5x5 piece tags 1–32 and corner markers 0–3.
    2. Click Run.
    3. Review the PGN and analysis.
    """)
    
    st.divider()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Settings")
        use_markers = st.checkbox("Use ArUco/AprilTag Markers", value=True, help="Requires markers on board corners")
        use_piece_tags = st.checkbox("Use piece tags (recommended)", value=True)
        if not use_piece_tags:
            st.warning("Occupancy recognition is experimental and needs a fixed camera and clear light/dark pieces.")
        motion_threshold = st.number_input("Motion Threshold", min_value=0.001, max_value=1.0, value=0.01, format="%.3f", help="Lower = more sensitive to motion")
        stable_duration = st.number_input("Stable Duration (s)", min_value=0.1, value=0.5, format="%.1f", help="How long board must be still")
        
    with col2:
        st.subheader("Upload Video")
        uploaded_file = st.file_uploader("Choose a video...", type=['mp4', 'mov', 'avi'])
        
        if uploaded_file is not None:
            if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
                params = {
                    "use_markers": use_markers,
                    "use_piece_tags": use_piece_tags,
                    "motion_threshold": motion_threshold,
                    "stable_duration": stable_duration
                }
                run_analysis(uploaded_file, params)

elif st.session_state.page == "results":
    if st.session_state.run_id:
        show_results(st.session_state.run_id)
    else:
        st.error("No run selected.")
        if st.button("Back to Home"):
            st.session_state.page = "home"
            st.rerun()
