"""
03_Schedule.py  —  Phase 3
View the full match bracket and schedule.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta, time
from modules.excel_sync import load_sheet
from modules.match_scheduler import generate_schedule, reset_schedule, schedule_finals_by_points, set_match_scheduled_date, set_match_scheduled_time
from modules.ui_helpers import render_logo, date_badge
from modules.team_builder import get_team_players
from modules import auth

render_logo()

st.title("📅 Match Schedule")
st.caption("Double-elimination pool play — top 2 by points fight for the championship.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load state for active sidebar location
# ---------------------------------------------------------------------------
loc = st.session_state.get("_location")
teams_df   = load_sheet("Teams", location=loc)
matches_df = load_sheet("Matches", location=loc)
players_df = load_sheet("Players", location=loc)

teams_exist   = not teams_df.empty
matches_exist = not matches_df.empty

# Build lookup maps
team_name = {}
if teams_exist:
    team_name = teams_df.set_index("team_id")["team_name"].to_dict()

# ---------------------------------------------------------------------------
# Generate schedule
# ---------------------------------------------------------------------------
if not teams_exist:
    st.warning("No teams found. Go to **Teams** and build balanced teams first.")
    st.stop()

if not matches_exist:
    st.subheader("Generate Bracket")
    n_teams  = len(teams_df)
    n_matches = n_teams // 2
    match_word = "match" if n_matches == 1 else "matches"
    st.info(
        f"{n_teams} teams ready. A random draw will create **{n_matches} {match_word}** in Round 1."
        + (" 1 team will receive a **bye** (auto-win)." if n_teams % 2 != 0 else "")
    )
    if auth.is_admin():
        if st.button("🎲 Generate Random Bracket", type="primary", width='stretch'):
            try:
                generate_schedule()
                st.success("Bracket generated!")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
    else:
        st.info("Unlock admin to generate the bracket.")
    st.stop()

# ---------------------------------------------------------------------------
# Display bracket
# ---------------------------------------------------------------------------
BRACKET_ORDER  = {"winners": 0, "losers": 1, "finals": 2, "bye": 3}
BRACKET_LABELS = {
    "winners": "🏅 Winners Bracket",
    "losers":  "🔄 Losers Bracket",
    "finals":  "🏆 Finals",
    "bye":     "⏭️ Bye",
}
STATUS_BADGE = {
    "scheduled":   "🕐 Scheduled",
    "in_progress": "⚡ In Progress",
    "done":        "✅ Done",
    "bye":         "⏭️ Bye",
}

def _team_label(tid):
    if tid is None or str(tid) == "nan":
        return "—"
    tname = team_name.get(int(tid), f"Team {int(tid)}")
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


# date_badge imported from ui_helpers

# Overall tournament stats strip
total    = len(matches_df[matches_df["bracket"] != "bye"])
done_cnt = int((matches_df["status"] == "done").sum())
active   = int((~teams_df["is_eliminated"].apply(
    lambda x: x is True or x == 1 or str(x).lower() == "true"
)).sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Matches", total)
c2.metric("Completed",     done_cnt)
c3.metric("Remaining",     total - done_cnt)
c4.metric("Teams Still In", active)
st.markdown("---")

# Sort and group
display_df = matches_df.copy()
display_df["_bracket_order"] = display_df["bracket"].map(
    lambda b: BRACKET_ORDER.get(str(b).lower(), 99)
)
display_df = display_df.sort_values(
    ["_bracket_order", "round", "match_id"]
).reset_index(drop=True)

current_bracket = None
current_round   = None
for _, row in display_df.iterrows():
    bracket   = str(row["bracket"]).lower()
    round_num = int(row["round"])

    if bracket != current_bracket:
        current_bracket = bracket
        current_round   = None          # reset round tracker on new bracket
        st.subheader(BRACKET_LABELS.get(bracket, bracket.title()))

    if round_num != current_round:
        current_round = round_num
        # Count matches in this round+bracket for the label
        round_match_count = len(
            display_df[
                (display_df["round"] == round_num) &
                (display_df["bracket"].str.lower() == bracket) &
                (display_df["bracket"].str.lower() != "bye")
            ]
        )
        round_match_word = "match" if round_match_count == 1 else "matches"
        st.markdown(f"**Round {round_num}** &nbsp;·&nbsp; {round_match_count} {round_match_word}")

    match_id  = int(row["match_id"])
    status    = str(row["status"])
    team_a    = _team_label(row["team_a_id"])
    team_b    = _team_label(row["team_b_id"])
    winner    = _team_label(row.get("winner_id"))
    sched_date = row.get("scheduled_date", None)

    # Build a card row — 4 columns: matchup | status | winner/date | (admin) date picker
    is_admin    = auth.is_admin()
    col_match, col_status, col_winner, col_date = st.columns([5, 2, 2, 3])

    if status == "bye":
        col_match.markdown(f"{team_a} — <em>bye (auto-win)</em>", unsafe_allow_html=True)
        col_status.markdown(STATUS_BADGE["bye"])
        col_winner.markdown(f"{team_a}", unsafe_allow_html=True)
    elif status == "done":
        sa = row.get("team_a_score", None)
        sb = row.get("team_b_score", None)
        score_str = ""
        if sa is not None and sb is not None and str(sa) != "nan" and str(sb) != "nan":
            score_str = f"  &nbsp;·&nbsp;  **{int(sa)} – {int(sb)}**"
        col_match.markdown(f"{team_a}  vs  {team_b}{score_str}", unsafe_allow_html=True)
        col_status.markdown(STATUS_BADGE["done"])
        col_winner.markdown(f"🏆 {winner}", unsafe_allow_html=True)
        # Show played date if available
        played = row.get("date_played", None)
        if played and str(played) not in ("", "nan", "None"):
            col_date.caption(f"Played {played}")
    else:
        # Scheduled / in-progress
        col_match.markdown(f"{team_a}  vs  {team_b}", unsafe_allow_html=True)
        col_status.markdown(STATUS_BADGE.get(status, status))
        col_winner.markdown("—")
        # Date badge for viewers; date picker for admin
        if is_admin:
            cur_val = None
            if sched_date and str(sched_date) not in ("", "nan", "None"):
                try:
                    cur_val = date.fromisoformat(str(sched_date))
                except ValueError:
                    cur_val = None
            new_date = col_date.date_input(
                "📅 Set date",
                value=cur_val,
                key=f"sched_date_{match_id}",
                label_visibility="collapsed",
            )
            if new_date != cur_val:
                set_match_scheduled_date(match_id, new_date)
                st.rerun()
            # Time input (admin)
            cur_time = None
            raw_t = row.get("scheduled_time", None)
            if raw_t and str(raw_t) not in ("", "nan", "None"):
                try:
                    cur_time = time.fromisoformat(str(raw_t))
                except Exception:
                    cur_time = None
            new_time = col_date.time_input(
                "⏰ Set time",
                value=cur_time,
                key=f"sched_time_{match_id}",
                label_visibility="collapsed",
            )
            if new_time != cur_time:
                set_match_scheduled_time(match_id, new_time)
                st.rerun()
        else:
            # Viewer: show date badge and the scheduled time (or TBD)
            sched_time = row.get("scheduled_time", None)
            time_text = sched_time if sched_time and str(sched_time) not in ("", "nan", "None") else "TBD"
            col_date.markdown(f"{date_badge(sched_date)}  \n**{time_text}**", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Champion banner
# ---------------------------------------------------------------------------
finals_rows = matches_df[matches_df["bracket"].str.lower() == "finals"] if not matches_df.empty else pd.DataFrame()
if not finals_rows.empty and str(finals_rows.iloc[0]["status"]) == "done":
    champion_id = int(finals_rows.iloc[0]["winner_id"])
    champion    = team_name.get(champion_id, f"Team {champion_id}")
    st.markdown("---")
    st.success(f"🎉 **Tournament Complete!** Champion: **{champion}** 🏆")

# ---------------------------------------------------------------------------
# Finals — auto-schedule (page-load fallback) or show live preview
# ---------------------------------------------------------------------------
else:
    pool_matches  = matches_df[matches_df["bracket"].str.lower().isin(["winners", "losers"])] if not matches_df.empty else pd.DataFrame()
    finals_exists = not finals_rows.empty
    pool_pending  = (pool_matches["status"] == "scheduled").any() if not pool_matches.empty else False
    any_played    = (matches_df["status"] == "done").any() if not matches_df.empty else False

    if any_played and not finals_exists and not pool_pending:
        # All pool matches done — auto-schedule finals (fallback if advance_bracket missed it)
        try:
            schedule_finals_by_points()
            st.rerun()
        except RuntimeError:
            pass

    elif any_played and not finals_exists:
        # Pool play still running — show read-only preview of current top 2
        done_m = matches_df[matches_df["status"] == "done"].copy()
        done_m["team_a_score"] = pd.to_numeric(done_m["team_a_score"], errors="coerce").fillna(0)
        done_m["team_b_score"] = pd.to_numeric(done_m["team_b_score"], errors="coerce").fillna(0)
        tp: dict = {}
        for _, r in done_m.iterrows():
            ta = int(r["team_a_id"]) if pd.notna(r["team_a_id"]) else None
            tb = int(r["team_b_id"]) if pd.notna(r["team_b_id"]) else None
            if ta: tp[ta] = tp.get(ta, 0) + int(r["team_a_score"])
            if tb: tp[tb] = tp.get(tb, 0) + int(r["team_b_score"])

        team_wins_map = teams_df.set_index("team_id")["wins"].to_dict() if not teams_df.empty else {}
        sorted_tids   = sorted(tp, key=lambda x: (tp[x], team_wins_map.get(x, 0)), reverse=True)

        if len(sorted_tids) >= 2:
            t1_id, t2_id = sorted_tids[0], sorted_tids[1]
            st.markdown("---")
            st.subheader("🏆 Finals")
            st.info(
                f"Pool play in progress. Current top 2 by points:  \n"
                f"**1. {team_name.get(t1_id, f'Team {t1_id}')}** — {tp[t1_id]} pts  \n"
                f"**2. {team_name.get(t2_id, f'Team {t2_id}')}** — {tp[t2_id]} pts  \n\n"
                f"Finals will be scheduled automatically once all pool matches are complete."
            )

# ---------------------------------------------------------------------------
# Reset bracket (admin)
# ---------------------------------------------------------------------------
st.markdown("---")
with st.expander("⚠️ Reset Entire Schedule"):
    st.warning(
        "This will delete all match records, clear all team wins/losses, "
        "and reset elimination statuses. Player and team registrations are kept."
    )
    if auth.is_admin():
        if st.button("🔄 Reset Schedule", type="secondary"):
            try:
                reset_schedule()
                st.success("Schedule reset. You can generate a new bracket now.")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))

