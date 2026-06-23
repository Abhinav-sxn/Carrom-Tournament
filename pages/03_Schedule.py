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
from modules.excel_sync import load_sheets
sheets = load_sheets(["Teams", "Matches", "Players"], location=loc)
teams_df   = sheets["Teams"]
matches_df = sheets["Matches"]
players_df = sheets["Players"]

# Initialize pending schedule changes
if "pending_schedule_changes" not in st.session_state:
    st.session_state["pending_schedule_changes"] = {}

# Merge pending changes into matches_df for real-time preview before saving
if not matches_df.empty and st.session_state["pending_schedule_changes"]:
    matches_df = matches_df.copy()
    matches_df["scheduled_date"] = matches_df["scheduled_date"].astype(object)
    matches_df["scheduled_time"] = matches_df.get("scheduled_time", None).astype(object)
    for (m_id, field), val in st.session_state["pending_schedule_changes"].items():
        if field == "date":
            val_str = str(val) if val is not None else None
            matches_df.loc[matches_df["match_id"].astype(int) == m_id, "scheduled_date"] = val_str
        elif field == "time":
            val_str = val.strftime("%H:%M") if val is not None else None
            matches_df.loc[matches_df["match_id"].astype(int) == m_id, "scheduled_time"] = val_str

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
        col_status.markdown("—")
        col_winner.markdown("—")
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
                st.session_state["pending_schedule_changes"][(match_id, "date")] = new_date
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
                st.session_state["pending_schedule_changes"][(match_id, "time")] = new_time
                st.rerun()
        else:
            # Viewer: show date badge and the scheduled time (or TBD)
            sched_time = row.get("scheduled_time", None)
            time_text = sched_time if sched_time and str(sched_time) not in ("", "nan", "None") else "TBD"
            col_date.markdown(f"{date_badge(sched_date)}  \n**{time_text}**", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Unsaved changes banner (admin only)
# ---------------------------------------------------------------------------
if auth.is_admin() and st.session_state.get("pending_schedule_changes"):
    st.markdown("---")
    st.warning("⚠️ You have unsaved schedule changes!")
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("💾 Save Schedule Changes", type="primary", use_container_width=True):
            from modules.excel_sync import save_sheet
            df = load_sheet("Matches")
            df["scheduled_date"] = df["scheduled_date"].astype(object)
            df["scheduled_time"] = df.get("scheduled_time", None).astype(object)
            
            for (m_id, field), val in st.session_state["pending_schedule_changes"].items():
                if field == "date":
                    val_str = str(val) if val is not None else None
                    df.loc[df["match_id"].astype(int) == m_id, "scheduled_date"] = val_str
                elif field == "time":
                    val_str = val.strftime("%H:%M") if val is not None else None
                    df.loc[df["match_id"].astype(int) == m_id, "scheduled_time"] = val_str
                    
            save_sheet("Matches", df)
            st.session_state["pending_schedule_changes"] = {}
            st.success("Schedule changes saved successfully!")
            st.rerun()
    with btn_col2:
        if st.button("🔄 Discard Changes", type="secondary", use_container_width=True):
            st.session_state["pending_schedule_changes"] = {}
            st.rerun()

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
# Adjust Match Pairings (admin)
# ---------------------------------------------------------------------------
if auth.is_admin() and matches_exist:
    st.markdown("---")
    with st.expander("🔀 Adjust Match Pairings"):
        st.subheader("Swap Match Teams")
        st.markdown(
            "Select a round and bracket, pick two scheduled matches, and choose which teams to swap."
        )
        
        # Filter matches that are "scheduled" or "in_progress" (not 'bye', not 'done')
        pending_matches = matches_df[matches_df["status"].isin(["scheduled", "in_progress"])].copy()
        
        if len(pending_matches) < 2:
            st.info("Need at least 2 scheduled or in-progress matches to adjust pairings.")
        else:
            # Group by (bracket, round)
            groups = []
            for (br, rd), grp in pending_matches.groupby(["bracket", "round"]):
                if len(grp) >= 2:
                    groups.append((br, rd))
            
            if not groups:
                st.info("No round has 2 or more scheduled/in-progress matches to swap.")
            else:
                # Let user select bracket/round
                group_options = [f"{br.title()} - Round {rd}" for br, rd in groups]
                selected_group_idx = st.selectbox(
                    "Select Round & Bracket",
                    range(len(group_options)),
                    format_func=lambda idx: group_options[idx],
                    key="swap_group_select"
                )
                br, rd = groups[selected_group_idx]
                
                # Get matches for selected group
                group_matches = pending_matches[
                    (pending_matches["bracket"] == br) & (pending_matches["round"] == rd)
                ].copy()
                
                # Format labels
                def _match_label(row):
                    m_id = int(row.match_id)
                    ta = team_name.get(int(row.team_a_id), f"Team {row.team_a_id}") if pd.notna(row.team_a_id) else "—"
                    tb = team_name.get(int(row.team_b_id), f"Team {row.team_b_id}") if pd.notna(row.team_b_id) else "—"
                    return f"Match {m_id}: {ta} vs {tb}"
                
                match_list = list(group_matches.itertuples())
                match_options = [(_match_label(m), m.match_id) for m in match_list]
                
                col1, col2 = st.columns(2)
                with col1:
                    m1_label, m1_id = st.selectbox(
                        "Match 1",
                        match_options,
                        format_func=lambda x: x[0],
                        key="swap_match_1"
                    )
                    # Load the actual row
                    row1 = group_matches[group_matches["match_id"] == m1_id].iloc[0]
                    t1_a_id = row1["team_a_id"]
                    t1_b_id = row1["team_b_id"]
                    
                    t1_a_name = team_name.get(int(t1_a_id), f"Team {t1_a_id}") if pd.notna(t1_a_id) else "—"
                    t1_b_name = team_name.get(int(t1_b_id), f"Team {t1_b_id}") if pd.notna(t1_b_id) else "—"
                    
                    swap_slot_1 = st.selectbox(
                        "Swap which team from Match 1?",
                        [("team_a_id", t1_a_name), ("team_b_id", t1_b_name)],
                        format_func=lambda x: f"Slot A: {x[1]}" if x[0] == "team_a_id" else f"Slot B: {x[1]}",
                        key="swap_slot_1"
                    )
                with col2:
                    # Filter out Match 1 from Match 2 options
                    m2_options = [opt for opt in match_options if opt[1] != m1_id]
                    if m2_options:
                        m2_label, m2_id = st.selectbox(
                            "Match 2",
                            m2_options,
                            format_func=lambda x: x[0],
                            key="swap_match_2"
                        )
                        # Load the actual row
                        row2 = group_matches[group_matches["match_id"] == m2_id].iloc[0]
                        t2_a_id = row2["team_a_id"]
                        t2_b_id = row2["team_b_id"]
                        
                        t2_a_name = team_name.get(int(t2_a_id), f"Team {t2_a_id}") if pd.notna(t2_a_id) else "—"
                        t2_b_name = team_name.get(int(t2_b_id), f"Team {t2_b_id}") if pd.notna(t2_b_id) else "—"
                        
                        swap_slot_2 = st.selectbox(
                            "Swap with which team from Match 2?",
                            [("team_a_id", t2_a_name), ("team_b_id", t2_b_name)],
                            format_func=lambda x: f"Slot A: {x[1]}" if x[0] == "team_a_id" else f"Slot B: {x[1]}",
                            key="swap_slot_2"
                        )
                    else:
                        m2_id = None
                
                if m2_id is not None:
                    if st.button("🔀 Swap Selected Teams", type="primary", use_container_width=True):
                        # Find indices in matches_df
                        idx1 = matches_df[matches_df["match_id"] == m1_id].index[0]
                        idx2 = matches_df[matches_df["match_id"] == m2_id].index[0]
                        
                        slot1_col = swap_slot_1[0]  # "team_a_id" or "team_b_id"
                        slot2_col = swap_slot_2[0]  # "team_a_id" or "team_b_id"
                        
                        val1 = matches_df.loc[idx1, slot1_col]
                        val2 = matches_df.loc[idx2, slot2_col]
                        
                        # Swap
                        matches_df.loc[idx1, slot1_col] = val2
                        matches_df.loc[idx2, slot2_col] = val1
                        
                        from modules.excel_sync import save_sheet
                        save_sheet("Matches", matches_df)
                        st.success(f"Successfully swapped team '{swap_slot_1[1]}' and team '{swap_slot_2[1]}'!")
                        st.rerun()

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

