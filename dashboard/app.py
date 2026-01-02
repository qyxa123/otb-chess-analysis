"""OTBReview Studio Streamlit entry point."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="OTBReview Studio",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("OTBReview Studio")
st.caption(
    "Beginner-friendly studio for converting over-the-board chess videos into interactive reviews."
)

st.markdown(
    """
    Use the sidebar to jump between pages:
    - **Home / New Analysis**: upload or drag in your video, select mode, and launch the pipeline.
    - **Review**: open the chess.com-style replay, eval bar, and downloads for any past run.
    - **Debug Lab**: developer space for inspecting corners, tags, and running quick reruns.
    - **Corrections**: human-in-the-loop fixes for board IDs and move-level tweaks.
    """
)

st.info(
    "Tip: every run is saved under `out/runs/<run_id>/` with all artifacts, so you never have to hunt for files.",
    icon="📂",
)

st.markdown(
    """
    ### Quick start
    1. Pick **Home / New Analysis** in the sidebar.
    2. Drop in an `.mp4` / `.mov`, choose **Marker** or **Tag** mode.
    3. Click **Analyze** and open the review once it finishes.
    """
)
