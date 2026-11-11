from __future__ import annotations

import io
import json
from pathlib import Path
from typing import List

import chess
import chess.pgn
import streamlit as st

from dashboard.utils import BASE_OUTDIR, load_board_sequences, load_json, run_history, write_run_metadata
from dashboard.correction_utils import regenerate_review, replace_move
from otbreview.pipeline.decode import decode_moves_from_tags
from otbreview.pipeline.pgn import generate_pgn, generate_moves_json
from otbreview.pipeline.analyze import analyze_game
from otbreview.pipeline.classify import classify_moves
from otbreview.pipeline.keymoves import find_key_moves
from otbreview.web.generate import generate_web_replay

st.title("Corrections")
st.caption("Fix board IDs early, override moves, and regenerate outputs.")

history = run_history()
run_ids = [item["run_id"] for item in history]
if not run_ids:
    st.info("No runs yet. Run an analysis first.")
    st.stop()

selected_id = st.selectbox("Select run", run_ids)
run_dir = BASE_OUTDIR / selected_id

def _save_override(board_states: List[List[List[int]]], selected_frame: int, edited_grid: List[List[int]]):
    override_path = run_dir / "board_ids_override.json"
    payload = board_states.copy()
    payload[selected_frame] = edited_grid
    override_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return override_path, payload


def _wrap_states(board_states: List[List[List[int]]]) -> List[dict]:
    return [{"piece_ids": grid} for grid in board_states]


def _render_board_editor(grid: List[List[int]]):
    st.markdown("#### Edit piece IDs")
    edited = []
    files = list("ABCDEFGH")
    for r in range(8):
        row = []
        cols = st.columns(8)
        for c in range(8):
            coord = f"{files[c]}{8-r}"
            row.append(
                cols[c].number_input(
                    coord,
                    min_value=0,
                    max_value=32,
                    value=int(grid[r][c]) if grid else 0,
                    key=f"cell_{selected_id}_{frame_idx}_{r}_{c}",
                    step=1,
                )
            )
        edited.append(row)
    return edited


board_states = load_board_sequences(run_dir / "board_ids_override.json")
if not board_states:
    board_states = load_board_sequences(run_dir / "board_ids.json")
if not board_states:
    board_states = load_board_sequences(run_dir / "debug" / "board_ids.json")

if not board_states:
    st.info("No board IDs are available for this run. You can still correct its PGN below.")
else:
    frame_idx = st.slider("Stable frame to correct", 0, len(board_states) - 1, 0) if len(board_states) > 1 else 0
    st.write(f"Editing frame #{frame_idx+1} / {len(board_states)}")
    edited_grid = _render_board_editor(board_states[frame_idx])

    if st.button("Save board_ids_override.json and re-decode", type="primary"):
        override_path, payload = _save_override(board_states, frame_idx, edited_grid)
        st.success(f"Saved overrides to {override_path}")
        try:
            wrapped_states = _wrap_states(payload)
            # Decode from the original starting position so earlier moves remain intact.
            moves, confidence = decode_moves_from_tags(wrapped_states, output_dir=str(run_dir / "debug"))
            if not moves or "??" in moves:
                raise ValueError("The corrected observations still contain unresolved moves. Check the board IDs.")
            warning = regenerate_review(run_dir, generate_pgn(moves), confidence, override_path)
            if warning:
                st.warning(warning)
            write_run_metadata(run_dir, {**load_json(run_dir / "run_meta.json"), "override_from_frame": frame_idx})
            st.success("Re-decoded moves and regenerated PGN/analysis/index.html.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Re-decode failed: {exc}")

st.divider()
st.subheader("Move-level correction")
pgn_path = run_dir / "game.pgn"
if not pgn_path.exists():
    st.info("Generate PGN first by decoding above.")
    st.stop()

pgn_content = pgn_path.read_text(encoding="utf-8")
game = chess.pgn.read_game(io.StringIO(pgn_content))
if game is None or game.errors:
    st.error("Could not parse PGN.")
    st.stop()

moves_list = list(game.mainline_moves())
if not moves_list:
    st.info("This PGN contains no moves to correct.")
    st.stop()
board = game.board()
for idx, move in enumerate(moves_list):
    board.push(move)

move_number = st.number_input("Move number to replace", min_value=1, max_value=len(moves_list), value=1)
board_reset = game.board()
for mv in moves_list[: move_number - 1]:
    board_reset.push(mv)

legal_san = [board_reset.san(mv) for mv in board_reset.legal_moves]
new_san = st.selectbox("Choose replacement SAN", legal_san)

if st.button("Apply move override"):
    try:
        pgn, discarded = replace_move(pgn_content, int(move_number), new_san)
        warning = regenerate_review(run_dir, pgn)
        if warning:
            st.warning(warning)
        if discarded:
            st.warning(f"Discarded {discarded} following plies that became illegal. Correct or re-decode the remaining game.")
        st.success("Move replaced and PGN, move trace, analysis, and replay regenerated.")
    except Exception as exc:
        st.error(f"Move correction failed: {exc}")
