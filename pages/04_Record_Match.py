"""
04_Record_Match.py  —  Phase 4
Umpire interface: record match result and assign per-player awards.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet, AWARDS
from modules.match_recorder import record_result, save_match_awards, get_match_awards
from modules.ui_helpers import render_logo

st.set_page_config(page_title="Record Match · Carrom Tournament", page_icon="🎮", layout="wide", initial_sidebar_state="expanded")
render_logo()

st.title("🎮 Record Match")
st.caption("Select a scheduled match, mark the winner, then assign player awards.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
matches_df  = load_sheet("Matches")
teams_df    = load_sheet("Teams")
players_df  = load_sheet("Players")

if matches_df.empty:
    st.warning("No matches scheduled yet. Go to **Schedule** to generate the bracket.")
    st.stop()

# Lookup helpers
team_name = teams_df.set_index("team_id")["team_name"].to_dict() if not teams_df.empty else {}

def _tname(tid):
    if tid is None or str(tid) == "nan":
        return "—"
    return team_name.get(int(tid), f"Team {int(tid)}")

def _tname_with_players(tid):
    """Return 'Team Name · Player1 & Player2' for richer labels."""
    if tid is None or str(tid) == "nan":
        return "—"
    name = team_name.get(int(tid), f"Team {int(tid)}")
    if not players_df.empty:
        members = players_df[players_df["team_id"] == int(tid)]["name"].tolist()
        if members:
            return f"{name}  ·  {' & '.join(members)}"
    return name

# ---------------------------------------------------------------------------
# Award label / description constants (used in record form)
# ---------------------------------------------------------------------------
AWARD_LABELS = {
    "queen_snatcher":   "👑 Queen Snatcher",
    "precision_player": "🎯 Precision Player",
    "best_striker":     "💥 Best Striker",
    "comeback_king":    "🔄 Comeback King",
}
AWARD_DESCRIPTIONS = {
    "queen_snatcher":   "Pocketed the Queen decisively",
    "precision_player": "Most consistently accurate shots",
    "best_striker":     "Most powerful and effective striking",
    "comeback_king":    "Turned the game around after a deficit",
}

BRACKET_ORDER = {"winners": 0, "losers": 1, "finals": 2, "bye": 3}
BRACKET_LABELS = {
    "winners": "🏅 Winners Bracket",
    "losers":  "🔄 Losers (Rematch)",
    "finals":  "🏆 Finals",
    "bye":     "⏭️ Bye",
}
STATUS_ICON = {
    "scheduled":   "🕐",
    "in_progress": "⚡",
    "done":        "✅",
    "bye":         "⏭️",
}

# ---------------------------------------------------------------------------
# Two-panel layout: bracket overview (left)  |  record form (right)
# ---------------------------------------------------------------------------
schedule_col, record_col = st.columns([1, 1.6], gap="large")

# ── LEFT: Live bracket overview ─────────────────────────────────────────────
with schedule_col:
    st.subheader("📅 Bracket Overview")

    if not matches_df.empty:
        total_m  = len(matches_df[matches_df["bracket"] != "bye"])
        done_cnt = int((matches_df["status"] == "done").sum())
        rem_cnt  = int((matches_df["status"] == "scheduled").sum())
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Done",      done_cnt)
        sc2.metric("Remaining", rem_cnt)
        sc3.metric("Total",     total_m)
        st.markdown("---")

        disp = matches_df.copy()
        disp["_bo"] = disp["bracket"].map(lambda b: BRACKET_ORDER.get(str(b).lower(), 99))
        disp = disp.sort_values(["_bo", "round", "match_id"]).reset_index(drop=True)

        cur_bracket = None
        cur_round   = None
        for _, row in disp.iterrows():
            bracket = str(row["bracket"]).lower()
            rnum    = int(row["round"])
            status  = str(row["status"])
            icon    = STATUS_ICON.get(status, "🕐")
            ta      = _tname(row["team_a_id"])
            tb      = _tname(row["team_b_id"])

            if bracket != cur_bracket:
                cur_bracket = bracket
                cur_round   = None
                st.markdown(f"**{BRACKET_LABELS.get(bracket, bracket.title())}**")

            if rnum != cur_round:
                cur_round = rnum
                st.caption(f"Round {rnum}")

            if status == "bye":
                st.markdown(f"{icon}&nbsp; {ta} — *bye*")
            elif status == "done":
                winner = _tname(row.get("winner_id"))
                st.markdown(
                    f"{icon}&nbsp; <span style='color:#6B7BB0'>{ta} vs {tb}</span>"
                    f" → **{winner}**",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"{icon}&nbsp; **{ta}** vs **{tb}**")
    else:
        st.info("No matches scheduled yet.")

# ── RIGHT: Record form ───────────────────────────────────────────────────────
with record_col:
    # ---- Match selector (only scheduled matches) ---------------------------
    scheduled = matches_df[matches_df["status"] == "scheduled"].copy()

    if scheduled.empty:
        active = teams_df[~teams_df["is_eliminated"].apply(
            lambda x: x is True or x == 1 or str(x).lower() == "true"
        )] if not teams_df.empty else pd.DataFrame()
        all_done = (matches_df["status"].isin(["done", "bye"])).all()
        if all_done and len(active) == 1:
            st.success(f"🏆 Tournament complete! Champion: **{active.iloc[0]['team_name']}**")
        else:
            st.info("No matches are currently scheduled. Results may still be pending from the current round.")
        st.stop()

    scheduled["label"] = scheduled.apply(
        lambda r: (
            f"Match {int(r['match_id'])}  —  "
            f"{_tname(r['team_a_id'])}  vs  {_tname(r['team_b_id'])}"
            f"  (Round {int(r['round'])}, {str(r['bracket']).capitalize()})"
        ),
        axis=1,
    )
    match_options     = dict(zip(scheduled["label"], scheduled["match_id"].astype(int)))
    selected_label    = st.selectbox("Select Match to Record", options=list(match_options.keys()))
    selected_match_id = match_options[selected_label]

    match_row = matches_df[matches_df["match_id"] == selected_match_id].iloc[0]
    team_a_id = int(match_row["team_a_id"])
    team_b_id = int(match_row["team_b_id"])

    st.markdown("---")

    # ---- Winner + awards in two sub-columns --------------------------------
    res_col, awards_col = st.columns([1, 2])

    with res_col:
        st.subheader("🏆 Result")
        opt_a = _tname_with_players(team_a_id)
        opt_b = _tname_with_players(team_b_id)
        winner_choice = st.radio("Who won?", options=[opt_a, opt_b], index=0)
        winner_id = team_a_id if winner_choice == opt_a else team_b_id
        loser_id  = team_b_id if winner_id == team_a_id else team_a_id

        st.markdown(
            f"**Winner:** {_tname(winner_id)}  \n"
            f"**Loser:** {_tname(loser_id)}"
        )

        if not teams_df.empty:
            is_finals = str(match_row["bracket"]).lower() == "finals"
            loser_row = teams_df[teams_df["team_id"] == loser_id]
            if not loser_row.empty:
                current_losses = int(loser_row.iloc[0].get("losses", 0) or 0)
                if is_finals:
                    st.error(f"⚠️ Finals — **{_tname(loser_id)}** will be **eliminated**.")
                elif current_losses + 1 >= 2:
                    st.error(f"⚠️ **{_tname(loser_id)}** will be **eliminated** (2nd loss).")
                else:
                    st.warning(f"ℹ️ {_tname(loser_id)} will have {current_losses + 1} loss — rematch next.")

    with awards_col:
        st.subheader("🎖️ Awards")
        st.caption("Multiple players can share different awards.")

        both_team_ids = [team_a_id, team_b_id]
        match_players = players_df[
            players_df["team_id"].isin(both_team_ids)
        ].reset_index(drop=True) if not players_df.empty else pd.DataFrame()

        award_map = {}

        if match_players.empty:
            st.info("No player data found.")
        else:
            existing_awards = get_match_awards(selected_match_id)
            existing_map = {}
            if not existing_awards.empty:
                for _, er in existing_awards.iterrows():
                    pid = int(er["player_id"])
                    existing_map[pid] = {a: int(er.get(a, 0) or 0) for a in AWARDS}

            for tid in both_team_ids:
                team_players = match_players[match_players["team_id"] == tid]
                members = team_players["name"].tolist()
                members_str = f"  ·  {' & '.join(members)}" if members else ""
                with st.expander(f"{_tname(tid)}{members_str}", expanded=True):
                    for _, p in team_players.iterrows():
                        pid   = int(p["player_id"])
                        pname = p["name"]
                        st.markdown(f"**{pname}**")
                        player_awards = {}
                        acols = st.columns(len(AWARDS))
                        for acol, award in zip(acols, AWARDS):
                            default = bool(existing_map.get(pid, {}).get(award, 0))
                            player_awards[award] = int(
                                acol.checkbox(
                                    AWARD_LABELS[award],
                                    value=default,
                                    key=f"{selected_match_id}_{pid}_{award}",
                                    help=AWARD_DESCRIPTIONS[award],
                                )
                            )
                        award_map[pid] = player_awards

    # ---- Submit ------------------------------------------------------------
    st.markdown("---")
    col_submit, col_spacer = st.columns([1, 3])
    with col_submit:
        if st.button("✅ Save Result & Awards", type="primary", use_container_width=True):
            try:
                record_result(selected_match_id, winner_id)
                if award_map:
                    save_match_awards(selected_match_id, award_map)
                st.success(
                    f"Match recorded! **{_tname(winner_id)}** wins.  \n"
                    f"Awards saved for {len(award_map)} player(s)."
                )
                st.balloons()
                st.rerun()
            except (ValueError, RuntimeError) as e:
                st.error(str(e))

