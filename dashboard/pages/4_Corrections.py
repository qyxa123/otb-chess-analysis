from __future__ import annotations

import json
from pathlib import Path
from typing import List

import chess
import chess.pgn
import streamlit as st

from dashboard.utils import load_board_sequences, load_json, run_history, write_run_metadata
from otbreview.pipeline.decode import decode_moves_from_tags
from otbreview.pipeline.pgn import generate_pgn, generate_moves_json
from otbreview.pipeline.analyze import analyze_game

st.title("Corrections")
st.caption("Fix board IDs early, override moves, and regenerate outputs.")

history = run_history()
run_ids = [item["run_id"] for item in history]
if not run_ids:
    st.info("No runs yet. Run an analysis first.")
    st.stop()

selected_id = st.selectbox("Select run", run_ids)
run_dir = Path("out/runs") / selected_id

def _save_override(board_states: List[List[List[int]]], selected_frame: int, edited_grid: List[List[int]]):
    override_path = run_dir / "board_ids_override.json"
    payload = board_states.copy()
    payload[selected_frame] = edited_grid
    override_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return override_path, payload


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
                    key=f"cell_{r}_{c}",
                    step=1,
                )
            )
        edited.append(row)
    return edited


board_states = load_board_sequences(run_dir / "board_ids.json")
if not board_states:
    board_states = load_board_sequences(run_dir / "debug" / "board_ids.json")

if not board_states:
    st.error("No board_ids.json found for this run.")
    st.stop()

frame_idx = st.slider("Stable frame to correct", 0, len(board_states) - 1, 0)
st.write(f"Editing frame #{frame_idx+1} / {len(board_states)}")
edited_grid = _render_board_editor(board_states[frame_idx])

if st.button("Save board_ids_override.json and re-decode", type="primary"):
    override_path, payload = _save_override(board_states, frame_idx, edited_grid)
    st.success(f"Saved overrides to {override_path}")
    try:
        moves, confidence = decode_moves_from_tags(payload[frame_idx:], output_dir=str(run_dir / "debug"))
        pgn = generate_pgn(moves)
        (run_dir / "game.pgn").write_text(pgn, encoding="utf-8")
        moves_json = generate_moves_json(moves)
        (run_dir / "moves.json").write_text(json.dumps(moves_json, indent=2), encoding="utf-8")
        analysis = analyze_game(str(run_dir / "game.pgn"))
        (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        write_run_metadata(run_dir, {**load_json(run_dir / "run_meta.json"), "override_from_frame": frame_idx})
        st.success("Re-decoded moves and regenerated PGN/analysis.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Re-decode failed: {exc}")

st.divider()
st.subheader("Move-level correction")
pgn_path = run_dir / "game.pgn"
if not pgn_path.exists():
    st.info("Generate PGN first by decoding above.")
    st.stop()

pgn_content = pgn_path.read_text(encoding="utf-8")
game = chess.pgn.read_game(iter(pgn_content.splitlines()))
if not game:
    st.error("Could not parse PGN.")
    st.stop()

moves_list = list(game.mainline_moves())
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
    replacement_move = None
    for mv in board_reset.legal_moves:
        if board_reset.san(mv) == new_san:
            replacement_move = mv
            break
    if replacement_move is None:
        st.error("Selected move not legal.")
    else:
        new_game_board = game.board()
        new_moves: List[str] = []
        for i in range(move_number - 1):
            move_obj = moves_list[i]
            new_game_board.push(move_obj)
            new_moves.append(new_game_board.san(move_obj))
        new_game_board.push(replacement_move)
        new_moves.append(new_game_board.san(replacement_move))
        for mv in moves_list[move_number:]:
            if mv in new_game_board.legal_moves:
                new_game_board.push(mv)
                new_moves.append(new_game_board.san(mv))
            else:
                break
        pgn = generate_pgn(new_moves)
        (run_dir / "game.pgn").write_text(pgn, encoding="utf-8")
        (run_dir / "moves.json").write_text(json.dumps(new_moves, indent=2), encoding="utf-8")
        analysis = analyze_game(str(run_dir / "game.pgn"))
        (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        st.success("Move replaced and outputs regenerated.")
