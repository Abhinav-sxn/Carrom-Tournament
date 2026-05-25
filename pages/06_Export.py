"""
06_Export.py
------------
Download the full tournament dataset as a styled Excel workbook.
The xlsx is generated in-memory on demand — no file is stored on disk.
"""

import streamlit as st
from modules.ui_helpers import render_logo
from modules.excel_sync import LOCATIONS, load_sheet
from modules.excel_export import generate_workbook_bytes
import datetime

st.set_page_config(
    page_title="Export · Carrom Tournament",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_logo()

st.title("📥 Export Tournament Data")
st.caption("Generate and download the complete dataset as a formatted Excel workbook.")

st.markdown("---")

col_loc, col_btn = st.columns([2, 3])

with col_loc:
    export_location = st.selectbox(
        "Location to export",
        options=LOCATIONS,
        index=0,
        key="export_location_select",
    )

# Preview row counts
players_df = load_sheet("Players")
teams_df   = load_sheet("Teams")
matches_df = load_sheet("Matches")

with col_btn:
    st.metric("Players",  len(players_df))

c1, c2, c3 = st.columns(3)
c1.metric("Teams",   len(teams_df))
c2.metric("Matches", len(matches_df))
c3.metric("Played",  int((matches_df["status"] == "done").sum()) if not matches_df.empty else 0)

st.markdown("---")

st.info(
    "The workbook contains **Players, Teams, Matches, MatchStats, Leaderboard, "
    "and PlayerStats** sheets — all styled and formatted.",
    icon="ℹ️",
)

xlsx_bytes = generate_workbook_bytes(export_location)
filename   = f"carrom_{export_location.lower()}_{datetime.date.today()}.xlsx"

st.download_button(
    label=f"⬇️ Download {export_location} — {filename}",
    data=xlsx_bytes,
    file_name=filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    width="stretch",
)
