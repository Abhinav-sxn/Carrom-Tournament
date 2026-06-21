"""
05_Leaderboard.py  —  Phase 5
Full tournament statistics: team standings and player award table.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet, AWARDS
from modules.leaderboard import get_team_standings, get_player_stats, get_award_leaders
from modules.ui_helpers import render_logo, grad_style, render_df

render_logo()

st.title("🏆 Leaderboard & Stats")
st.caption("Live team standings, elimination tracker, and player award totals.")
st.markdown("---")

def render_leaderboard():
    # ---------------------------------------------------------------------------
    # Sync active location for this fragment execution thread
    # ---------------------------------------------------------------------------
    from modules.excel_sync import LOCATIONS, set_location
    loc = st.session_state.get("_location", LOCATIONS[0])
    set_location(loc)

    # ---------------------------------------------------------------------------
    # Load data in parallel
    # ---------------------------------------------------------------------------
    from modules.excel_sync import load_sheets
    sheets = load_sheets(["Leaderboard", "PlayerStats", "Teams", "Matches"])
    lb_df  = sheets["Leaderboard"]
    ps_df  = sheets["PlayerStats"]
    teams_df   = sheets["Teams"]
    matches_df = sheets["Matches"]
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

    if not teams_df.empty and not matches_df.empty:
        finals_rows = matches_df[matches_df["bracket"].str.lower() == "finals"]
        if not finals_rows.empty and str(finals_rows.iloc[0]["status"]) == "done":
            champion_id = int(finals_rows.iloc[0]["winner_id"])
            champion_name = teams_df.set_index("team_id")["team_name"].to_dict().get(champion_id, f"Team {champion_id}")
            st.success(f"🎉 Tournament Complete! Champion: **{champion_name}** 🏆")
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
            display["wins"]         = pd.to_numeric(display["wins"],         errors="coerce").fillna(0).astype(int)
            display["losses"]       = pd.to_numeric(display["losses"],       errors="coerce").fillna(0).astype(int)
            display["total_points"] = pd.to_numeric(display.get("total_points", 0), errors="coerce").fillna(0).astype(int)
            display["total_awards"] = pd.to_numeric(display["total_awards"], errors="coerce").fillna(0).astype(int)

            # Sort display by points (descending), then wins (descending), then losses (ascending)
            display = display.sort_values(
                ["total_points", "wins", "losses"],
                ascending=[False, False, True]
            ).reset_index(drop=True)

            # Status badge
            display["Status"] = display["status"].apply(
                lambda s: "❌ Eliminated" if s == "Eliminated" else "✅ Active"
            )
            display = display.rename(columns={
                "team_name":    "Team",
                "wins":         "Wins",
                "losses":       "Losses",
                "total_points": "Points",
                "total_awards": "Awards",
            })
            display["Rank"] = range(1, len(display) + 1)
            display = display[["Rank", "Team", "Points", "Wins", "Losses", "Awards", "Status"]]

            render_df(
                grad_style(
                    display.style,
                    (["Points"], "wins"),
                    (["Wins"],   "wins"),
                    (["Losses"], "losses"),
                ),
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
                grad_style(display_ps.style, (["Total"], "awards")),
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
            done = matches_df[matches_df["status"] == "done"].copy()
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

render_leaderboard()

