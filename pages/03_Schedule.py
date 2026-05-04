"""
03_Schedule.py  —  Phase 3
View the full match bracket and schedule.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet
from modules.match_scheduler import generate_schedule, reset_schedule
from modules.ui_helpers import render_logo

st.set_page_config(page_title="Schedule · Carrom Tournament", page_icon="📅", layout="wide", initial_sidebar_state="expanded")
render_logo()

st.title("📅 Match Schedule")
st.caption("Double-elimination bracket — 2 losses and a team is out.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load state
# ---------------------------------------------------------------------------
teams_df   = load_sheet("Teams")
matches_df = load_sheet("Matches")
players_df = load_sheet("Players")

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
    if st.button("🎲 Generate Random Bracket", type="primary", use_container_width=True):
        try:
            generate_schedule()
            st.success("Bracket generated!")
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))
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
    return team_name.get(int(tid), f"Team {int(tid)}")

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

    # Build a card row
    col_match, col_status, col_winner = st.columns([5, 2, 2])

    if status == "bye":
        col_match.markdown(f"**{team_a}** — *bye (auto-win)*")
        col_status.markdown(STATUS_BADGE["bye"])
        col_winner.markdown(f"**{team_a}**")
    elif status == "done":
        col_match.markdown(f"**{team_a}**  vs  **{team_b}**")
        col_status.markdown(STATUS_BADGE["done"])
        col_winner.markdown(f"🏆 **{winner}**")
    else:
        col_match.markdown(f"**{team_a}**  vs  **{team_b}**")
        col_status.markdown(STATUS_BADGE.get(status, status))
        col_winner.markdown("—")

# ---------------------------------------------------------------------------
# Tournament winner banner
# ---------------------------------------------------------------------------
active_teams = teams_df[~teams_df["is_eliminated"].apply(
    lambda x: x is True or x == 1 or str(x).lower() == "true"
)]
all_done = (matches_df["status"].isin(["done", "bye"])).all()

if all_done and len(active_teams) == 1:
    champion = active_teams.iloc[0]["team_name"]
    st.markdown("---")
    st.success(f"🎉 **Tournament Complete!** Champion: **{champion}** 🏆")

# ---------------------------------------------------------------------------
# Reset bracket (admin)
# ---------------------------------------------------------------------------
st.markdown("---")
with st.expander("⚠️ Reset Entire Schedule"):
    st.warning(
        "This will delete all match records, clear all team wins/losses, "
        "and reset elimination statuses. Player and team registrations are kept."
    )
    if st.button("🔄 Reset Schedule", type="secondary"):
        try:
            reset_schedule()
            st.success("Schedule reset. You can generate a new bracket now.")
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))

