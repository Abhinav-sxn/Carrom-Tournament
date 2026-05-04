"""
05_Leaderboard.py  —  Phase 5
Full tournament statistics: team standings and player award table.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet, AWARDS
from modules.leaderboard import get_team_standings, get_player_stats, get_award_leaders
from modules.ui_helpers import render_logo, get_cmaps, render_df

st.set_page_config(page_title="Leaderboard · Carrom Tournament", page_icon="🏆", layout="wide", initial_sidebar_state="expanded")
render_logo()

st.title("🏆 Leaderboard & Stats")
st.caption("Live team standings, elimination tracker, and player award totals.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
lb_df  = get_team_standings()
ps_df  = get_player_stats()
leaders = get_award_leaders()

AWARD_LABELS = {
    "queen_snatcher":   "👑 Queen Snatcher",
    "precision_player": "🎯 Precision Player",
    "best_striker":     "💥 Best Striker",
    "comeback_king":    "🔄 Comeback King",
}

# ---------------------------------------------------------------------------
# Tournament champion banner (if complete)
# ---------------------------------------------------------------------------
teams_df   = load_sheet("Teams")
matches_df = load_sheet("Matches")

if not teams_df.empty and not matches_df.empty:
    active = teams_df[~teams_df["is_eliminated"].apply(
        lambda x: x is True or x == 1 or str(x).lower() == "true"
    )]
    all_done = matches_df["status"].isin(["done", "bye"]).all()
    if all_done and len(active) == 1:
        st.success(f"🎉 Tournament Complete! Champion: **{active.iloc[0]['team_name']}** 🏆")
        st.markdown("---")

# ---------------------------------------------------------------------------
# Award leaders strip
# ---------------------------------------------------------------------------
st.subheader("🎖️ Award Leaders")
if all(v["count"] == 0 for v in leaders.values()):
    st.info("No awards assigned yet — record matches on the **Record Match** page.")
else:
    cols = st.columns(len(AWARDS))
    for col, award in zip(cols, AWARDS):
        leader = leaders[award]
        col.metric(
            label=AWARD_LABELS[award],
            value=leader["name"],
            delta=f"{leader['count']}x" if leader["count"] > 0 else None,
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Two-column: team standings + player stats
# ---------------------------------------------------------------------------
left, right = st.columns(2)

# ---- Team Standings --------------------------------------------------------
with left:
    st.subheader("📊 Team Standings")
    if lb_df.empty:
        st.info("No teams yet.")
    else:
        display = lb_df.copy()
        display["wins"]   = pd.to_numeric(display["wins"],   errors="coerce").fillna(0).astype(int)
        display["losses"] = pd.to_numeric(display["losses"], errors="coerce").fillna(0).astype(int)
        display["total_awards"] = pd.to_numeric(display["total_awards"], errors="coerce").fillna(0).astype(int)

        # Status badge
        display["Status"] = display["status"].apply(
            lambda s: "❌ Eliminated" if s == "Eliminated" else "✅ Active"
        )
        display = display.rename(columns={
            "rank":         "Rank",
            "team_name":    "Team",
            "wins":         "Wins",
            "losses":       "Losses",
            "total_awards": "Awards",
        })
        display = display[["Rank", "Team", "Wins", "Losses", "Awards", "Status"]]

        _cm = get_cmaps()
        render_df(
            display.style
                .background_gradient(subset=["Wins"], cmap=_cm["wins"])
                .background_gradient(subset=["Losses"], cmap=_cm["losses"]),
        )

# ---- Player Stats ----------------------------------------------------------
with right:
    st.subheader("👤 Player Award Totals")
    if ps_df.empty:
        st.info("No player data yet.")
    else:
        display_ps = ps_df.copy()
        for col in AWARDS + ["total_awards"]:
            if col in display_ps.columns:
                display_ps[col] = pd.to_numeric(display_ps[col], errors="coerce").fillna(0).astype(int)

        # Rename award columns to short emoji labels
        rename_map = {a: AWARD_LABELS[a].split(" ", 1)[0] for a in AWARDS}
        rename_map["name"]         = "Player"
        rename_map["team_name"]    = "Team"
        rename_map["total_awards"] = "Total"
        display_ps = display_ps.rename(columns=rename_map)

        cols_to_show = ["Player", "Team"] + [AWARD_LABELS[a].split(" ", 1)[0] for a in AWARDS] + ["Total"]
        display_ps = display_ps[cols_to_show].sort_values("Total", ascending=False).reset_index(drop=True)
        display_ps.index += 1

        render_df(
            display_ps.style.background_gradient(subset=["Total"], cmap=get_cmaps()["awards"]),
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Per-award breakdown — who has won each award and how many times
# ---------------------------------------------------------------------------
st.subheader("🏅 Award Breakdown")
if ps_df.empty or all(ps_df[a].sum() == 0 for a in AWARDS if a in ps_df.columns):
    st.info("No awards recorded yet.")
else:
    award_cols = st.columns(len(AWARDS))
    for col, award in zip(award_cols, AWARDS):
        with col:
            st.markdown(f"**{AWARD_LABELS[award]}**")
            if award in ps_df.columns:
                adf = (
                    ps_df[ps_df[award] > 0][["name", award]]
                    .sort_values(award, ascending=False)
                    .reset_index(drop=True)
                )
                adf.columns = ["Player", "Count"]
                adf.index += 1
                if adf.empty:
                    st.caption("None yet")
                else:
                    render_df(adf, hide_index=False)
            else:
                st.caption("No data")

st.markdown("---")

# ---------------------------------------------------------------------------
# Full match history
# ---------------------------------------------------------------------------
with st.expander("📋 Full Match History", expanded=False):
    if matches_df.empty:
        st.info("No matches played yet.")
    else:
        done = matches_df[matches_df["status"].isin(["done", "bye"])].copy()
        if done.empty:
            st.info("No completed matches yet.")
        else:
            name_map = teams_df.set_index("team_id")["team_name"].to_dict() if not teams_df.empty else {}
            def _tname(tid):
                if tid is None or str(tid) == "nan": return "—"
                return name_map.get(int(tid), f"Team {int(tid)}")

            done["Team A"]   = done["team_a_id"].apply(_tname)
            done["Team B"]   = done["team_b_id"].apply(_tname)
            done["Winner"]   = done["winner_id"].apply(_tname)
            done["Bracket"]  = done["bracket"].str.capitalize()
            done["Date"]     = done["date_played"].fillna("—")
            history = done[["match_id", "round", "Bracket", "Team A", "Team B", "Winner", "Date"]]
            history.columns  = ["Match", "Round", "Bracket", "Team A", "Team B", "Winner", "Date"]
            render_df(history.reset_index(drop=True))

