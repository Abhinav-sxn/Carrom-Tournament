"""
main.py  —  Carrom Tournament Manager
Home dashboard: live stats, team standings, recent results.
Run with:  streamlit run main.py
           (or double-click run.bat on Windows)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st
from modules.excel_sync import init_workbook, load_sheet, LOCATIONS
from modules.ui_helpers import render_logo, render_df, date_badge
from modules.team_builder import get_team_players
from modules import auth

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


def _home():
    render_logo()      # sets active location first
    init_workbook()    # creates location-specific CSV files if they don't exist

    @st.fragment(run_every=5)
    def render_dashboard():
        # ---------------------------------------------------------------------------
        # Load data for the active location (explicit to avoid thread-local mismatches)
        # ---------------------------------------------------------------------------
        loc = st.session_state.get("_location", LOCATIONS[0])
        from modules.excel_sync import load_sheets
        sheets = load_sheets(["Players", "Teams", "Matches", "MatchStats"], location=loc)
        players_df = sheets["Players"]
        teams_df   = sheets["Teams"]
        matches_df = sheets["Matches"]
        ms_df      = sheets["MatchStats"]

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
            finals_rows = matches_df[matches_df["bracket"].str.lower() == "finals"]
            if not finals_rows.empty and str(finals_rows.iloc[0]["status"]) == "done":
                champion_id   = int(finals_rows.iloc[0]["winner_id"])
                champion_name = teams_df.set_index("team_id")["team_name"].to_dict().get(champion_id, f"Team {champion_id}")
                st.success(f"🎉 Tournament Complete! Champion: **{champion_name}** 🏆")
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

        # ---------------------------------------------------------------------------
        # Upcoming match alert (grouped and numbered by date)
        # ---------------------------------------------------------------------------
        if not matches_df.empty:
            upcoming = matches_df[
                (matches_df["status"] == "scheduled") &
                (matches_df["bracket"].str.lower() != "bye")
            ].copy()

            if not upcoming.empty and not teams_df.empty:
                # normalize scheduled_date to datetimes for robust sorting (accept day-first formats)
                upcoming["_sched_dt"] = pd.to_datetime(upcoming.get("scheduled_date", None), dayfirst=True, errors="coerce")
                upcoming["_sched_date"] = upcoming["_sched_dt"].dt.date
                # create a combined datetime (date + time) when time is provided; leave NaT when time is missing
                upcoming["_sched_dt_time"] = pd.NaT
                has_time = upcoming.get("scheduled_time").notna() & (upcoming.get("scheduled_time").astype(str).str.strip() != "")
                if has_time.any():
                    combined = (upcoming.loc[has_time, "scheduled_date"].astype(str).str.strip()
                                + " " + upcoming.loc[has_time, "scheduled_time"].astype(str).str.strip())
                    upcoming.loc[has_time, "_sched_dt_time"] = pd.to_datetime(combined, dayfirst=True, errors="coerce")

                # sort by date then time (timed matches first). Use stable sort to preserve deterministic ordering.
                upcoming = upcoming.sort_values(["_sched_dt", "_sched_dt_time", "round", "match_id"], na_position="last", kind="mergesort")

                name_map = teams_df.set_index("team_id")["team_name"].to_dict()
                def _team_label(tid):
                    if pd.isna(tid):
                        return "—"
                    tname = name_map.get(int(tid), f"Team {int(tid)}")
                    try:
                        players = get_team_players(int(tid))
                        firsts = []
                        for _, p in players.iterrows():
                            raw = str(p.get("name") or "").strip()
                            if raw:
                                firsts.append(raw.split()[0])
                        if firsts:
                            names_html = " &amp; ".join(firsts)
                            return f"<strong>{tname}</strong> <span style=\"font-style:italic;font-size:0.9em\">({names_html})</span>"
                    except Exception:
                        pass
                    return f"<strong>{tname}</strong>"

                st.markdown("##### ⚡ Upcoming Matches")
                # Build an explicit list of unique dates in chronological order (NaT last)
                ordered = upcoming.dropna(subset=["_sched_dt"]).sort_values("_sched_dt")
                ordered_dates = list(dict.fromkeys(ordered["_sched_dt"].dt.date))
                if upcoming["_sched_date"].isna().any():
                    ordered_dates = ordered_dates + [None]

                for sched_date in ordered_dates:
                    if pd.notna(sched_date):
                        group = upcoming[upcoming["_sched_date"] == sched_date]
                    else:
                        group = upcoming[upcoming["_sched_date"].isna()]

                    # display a header for the date (use date_badge to get consistent styling)
                    badge = date_badge(sched_date.isoformat()) if pd.notna(sched_date) else "—"
                    if badge != "—":
                        st.markdown(f"**{badge}**", unsafe_allow_html=True)
                    else:
                        st.markdown("**Unscheduled**")

                    # enumerate matches for this date (1-based). Ensure group is sorted by time within the date
                    group = group.sort_values(["_sched_dt_time", "round", "match_id"], na_position="last", kind="mergesort")
                    for idx, (_, um) in enumerate(group.iterrows(), start=1):
                        with st.container(border=True):
                            # display per-date index as the match number; include the date for clarity
                            date_text = sched_date.strftime('%d %b %Y') if pd.notna(sched_date) else "Unscheduled"
                            sched_time = um.get("scheduled_time", None)
                            if sched_time and str(sched_time) not in ("", "nan", "None"):
                                time_part = f"@ {str(sched_time)}"
                            else:
                                time_part = "· TBD"
                            st.markdown(
                                f"**Match {idx}** &nbsp;·&nbsp; Round {int(um['round'])} &nbsp;·&nbsp; {date_text} &nbsp;{time_part}  \n"
                                f"🎯 &nbsp; {_team_label(um['team_a_id'])} &nbsp; vs &nbsp; {_team_label(um['team_b_id'])}",
                                unsafe_allow_html=True,
                            )

        st.markdown("---")

        # ---------------------------------------------------------------------------
        # Two-column body
        # ---------------------------------------------------------------------------
        left, right = st.columns(2)

        # ---- Team Standings --------------------------------------------------------
        with left:
            st.subheader("🏆 Team Standings")
            if not teams_df.empty:
                display = teams_df[["team_id", "team_name", "wins", "losses", "is_eliminated"]].copy()
                display["wins"]   = pd.to_numeric(display["wins"],   errors="coerce").fillna(0).astype(int)
                display["losses"] = pd.to_numeric(display["losses"], errors="coerce").fillna(0).astype(int)

                # Compute total points per team from all completed matches
                if not matches_df.empty:
                    done_m = matches_df[matches_df["status"] == "done"].copy()
                    done_m["team_a_score"] = pd.to_numeric(done_m.get("team_a_score", 0), errors="coerce").fillna(0)
                    done_m["team_b_score"] = pd.to_numeric(done_m.get("team_b_score", 0), errors="coerce").fillna(0)
                    sa = done_m[["team_a_id", "team_a_score"]].rename(columns={"team_a_id": "team_id", "team_a_score": "pts"})
                    sb = done_m[["team_b_id", "team_b_score"]].rename(columns={"team_b_id": "team_id", "team_b_score": "pts"})
                    all_pts = pd.concat([sa, sb], ignore_index=True).dropna(subset=["team_id"])
                    all_pts["team_id"] = pd.to_numeric(all_pts["team_id"], errors="coerce")
                    team_pts = all_pts.groupby("team_id")["pts"].sum().reset_index(name="Points")
                    display = display.merge(team_pts, on="team_id", how="left")
                else:
                    display["Points"] = 0
                display["Points"] = display["Points"].fillna(0).astype(int)

                display["Status"] = display["is_eliminated"].apply(
                    lambda x: "❌ Eliminated" if (x is True or x == 1) else "✅ Active"
                )
                display = display.drop(columns=["is_eliminated", "team_id"])
                display.columns = ["Team", "Wins", "Losses", "Points", "Status"]
                display = (
                    display
                    .sort_values(["Wins", "Losses", "Points"], ascending=[False, True, False])
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
                    # Render recent results as markdown lines using HTML labels
                    def _label_for_row(tid):
                        return _team_label(tid)

                    done["Bracket"] = done["bracket"].str.capitalize()
                    recent = done[["round", "team_a_id", "team_b_id", "winner_id", "Bracket"]].tail(5)
                    recent.columns = ["Round", "Team A ID", "Team B ID", "Winner ID", "Bracket"]
                    for _, r in recent.iterrows():
                        round_no = int(r["Round"])
                        ta = _label_for_row(r["Team A ID"]) if pd.notna(r["Team A ID"]) else "—"
                        tb = _label_for_row(r["Team B ID"]) if pd.notna(r["Team B ID"]) else "—"
                        winner = _label_for_row(r["Winner ID"]) if pd.notna(r["Winner ID"]) else "—"
                        st.markdown(
                            f"**Round {round_no}** — {ta}  vs  {tb}  ·  Winner: {winner}",
                            unsafe_allow_html=True,
                        )
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

    render_dashboard()


# ---------------------------------------------------------------------------
# Navigation — admin-only pages are hidden until admin logs in
# ---------------------------------------------------------------------------
_admin_pages = [
    st.Page("pages/01_Players.py",      title="Players",      icon="👤"),
    st.Page("pages/02_Teams.py",        title="Teams",        icon="🤝"),
    st.Page("pages/03_Schedule.py",     title="Schedule",     icon="📅"),
    st.Page("pages/04_Record_Match.py", title="Record Match", icon="🎮"),
    st.Page("pages/06_Export.py",       title="Export",       icon="📥"),
]

pages = [st.Page(_home, title="Home", icon="🎯", default=True)]
if auth.is_admin():
    pages += _admin_pages
pages.append(st.Page("pages/05_Leaderboard.py", title="Leaderboard", icon="🏆"))

pg = st.navigation(pages)
pg.run()
