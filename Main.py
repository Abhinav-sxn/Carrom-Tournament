"""
main.py  —  Carrom Tournament Manager
Home dashboard: live stats, team standings, recent results.
Run with:  streamlit run main.py
           (or double-click run.bat on Windows)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from modules.excel_sync import init_workbook, load_sheet
from modules.ui_helpers import render_logo, render_df

# ---------------------------------------------------------------------------
# Page config  (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Carrom Tournament",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Bootstrap workbook on first run
# ---------------------------------------------------------------------------
render_logo()      # sets active location first
init_workbook()    # creates location-specific .xlsx if it doesn't exist

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
players_df = load_sheet("Players")
teams_df   = load_sheet("Teams")
matches_df = load_sheet("Matches")
ms_df      = load_sheet("MatchStats")

total_players  = len(players_df)
total_teams    = len(teams_df)
total_matches  = len(matches_df)
played_matches = (
    int((matches_df["status"] == "done").sum())
    if not matches_df.empty else 0
)
remaining_matches = total_matches - played_matches

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="padding: 1.2rem 0 0.4rem 0;">
        <h1 style="margin: 0; font-size: 2.6rem; font-weight: 800; color: #FFFFFF;">
            \U0001f3af&nbsp;<span style="color: #FFFFFF;">Carrom Board </span><span style="color: #7C3AED;">Tournament</span>
        </h1>
        <p style="margin: 0.35rem 0 0 0; color: #6B7BB0; font-size: 0.95rem; font-weight: 400;">
            Manage players &nbsp;·&nbsp; schedule matches &nbsp;·&nbsp; track every award
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("---")

# ---------------------------------------------------------------------------
# Tournament champion banner
# ---------------------------------------------------------------------------
if not teams_df.empty and not matches_df.empty:
    active = teams_df[~teams_df["is_eliminated"].apply(
        lambda x: x is True or x == 1 or str(x).lower() == "true"
    )]
    all_done = matches_df["status"].isin(["done", "bye"]).all()
    if all_done and len(active) == 1:
        st.success(f"🎉 Tournament Complete! Champion: **{active.iloc[0]['team_name']}** 🏆")
        st.markdown("---")

# ---------------------------------------------------------------------------
# Top-level metrics
# ---------------------------------------------------------------------------
active_teams = int((~teams_df["is_eliminated"].apply(
    lambda x: x is True or x == 1 or str(x).lower() == "true"
)).sum()) if not teams_df.empty else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Players Registered", total_players)
c2.metric("Teams Active", active_teams, delta=f"{total_teams - active_teams} eliminated" if total_teams > 0 else None)
c3.metric("Matches Played", played_matches)
c4.metric("Matches Remaining", remaining_matches)

st.markdown("---")

# ---------------------------------------------------------------------------
# Two-column body
# ---------------------------------------------------------------------------
left, right = st.columns(2)

# ---- Team Standings --------------------------------------------------------
with left:
    st.subheader("🏆 Team Standings")
    if not teams_df.empty:
        display = teams_df[["team_name", "wins", "losses", "is_eliminated"]].copy()
        display["wins"]   = display["wins"].fillna(0).astype(int)
        display["losses"] = display["losses"].fillna(0).astype(int)
        display["Status"] = display["is_eliminated"].apply(
            lambda x: "❌ Eliminated" if (x is True or x == 1) else "✅ Active"
        )
        display = display.drop(columns=["is_eliminated"])
        display.columns = ["Team", "Wins", "Losses", "Status"]
        display = (
            display
            .sort_values(["Wins", "Losses"], ascending=[False, True])
            .reset_index(drop=True)
        )
        display.index += 1
        render_df(display, hide_index=False)
    else:
        st.info("No teams yet — head to **Teams** to build balanced pairs.")

# ---- Recent Results --------------------------------------------------------
with right:
    st.subheader("📋 Recent Match Results")
    if not matches_df.empty:
        done = matches_df[matches_df["status"] == "done"].copy()
        if not done.empty and not teams_df.empty:
            name_map = teams_df.set_index("team_id")["team_name"].to_dict()
            done["Team A"]  = done["team_a_id"].map(name_map)
            done["Team B"]  = done["team_b_id"].map(name_map)
            done["Winner"]  = done["winner_id"].map(name_map)
            done["Bracket"] = done["bracket"].str.capitalize()
            recent = done[["round", "Team A", "Team B", "Winner", "Bracket"]].tail(5)
            recent.columns = ["Round", "Team A", "Team B", "Winner", "Bracket"]
            render_df(recent.reset_index(drop=True))
        else:
            st.info("No completed matches yet.")
    else:
        st.info("No matches scheduled yet — head to **Schedule** to generate the bracket.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Award leaders strip (shows only if match stats exist)
# ---------------------------------------------------------------------------
if not ms_df.empty and not players_df.empty:
    from modules.excel_sync import AWARDS

    st.subheader("🎖️ Current Award Leaders")
    award_labels = {
        "queen_snatcher":   "👑 Queen Snatcher",
        "precision_player": "🎯 Precision Player",
        "best_striker":     "💥 Best Striker",
        "comeback_king":    "🔄 Comeback King",
    }

    # Compute per-player totals
    totals = (
        ms_df.dropna(subset=["player_id"])
        .groupby("player_id")[AWARDS]
        .sum()
        .reset_index()
    )
    totals = totals.merge(
        players_df[["player_id", "name"]], on="player_id", how="left"
    )

    cols = st.columns(len(AWARDS))
    for col, award in zip(cols, AWARDS):
        if totals[award].sum() > 0:
            top_row = totals.loc[totals[award].idxmax()]
            col.metric(
                label=award_labels[award],
                value=top_row["name"],
                delta=f"{int(top_row[award])}x",
            )
        else:
            col.metric(label=award_labels[award], value="—")

    st.markdown("---")

# ---------------------------------------------------------------------------
# Quick-start guide (shown only when no data exists yet)
# ---------------------------------------------------------------------------
if total_players == 0:
    st.markdown("---")
    st.subheader("🚀 Getting Started")
    st.markdown("""
Follow these steps to run your tournament:

| Step | Page | Action |
|------|------|--------|
| 1️⃣ | **Players** | Add all participants with skill ratings (1–10) |
| 2️⃣ | **Teams** | Preview balanced 2v2 pairings, confirm & name teams |
| 3️⃣ | **Schedule** | Generate the random double-elimination bracket |
| 4️⃣ | **Record Match** | After each match, mark the winner & assign player awards |
| 5️⃣ | **Leaderboard** | Track live standings, award leaders & full stats |

> 💡 All data is saved automatically to `data/tournament.xlsx` — share it for offline viewing.
""")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.caption(f"Data file: `{os.path.relpath(os.path.join('data', 'tournament.xlsx'))}`  •  Carrom Tournament Manager")
