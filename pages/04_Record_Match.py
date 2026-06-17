"""
04_Record_Match.py  —  Phase 4
Umpire interface: record match result and assign per-player awards.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet, AWARDS
from modules.match_recorder import record_result, save_match_awards, get_match_awards, edit_match_result
from modules.ui_helpers import render_logo
from modules import auth

render_logo()

st.title("🎮 Record Match")
st.caption("Select a scheduled match, mark the winner, then assign player awards.")
st.markdown("---")

# Shrink the inline edit buttons (secondary type) in the bracket overview
st.markdown("""
<style>
[data-testid="stBaseButton-secondary"] {
    padding-top: 0.05rem !important;
    padding-bottom: 0.05rem !important;
    font-size: 0.7rem !important;
    min-height: 0 !important;
    color: #888 !important;
    border-color: #ccc !important;
    background: transparent !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load data for active sidebar location
# ---------------------------------------------------------------------------
loc = st.session_state.get("_location")
from modules.excel_sync import load_sheets
sheets = load_sheets(["Matches", "Teams", "Players"], location=loc)
matches_df  = sheets["Matches"]
teams_df    = sheets["Teams"]
players_df  = sheets["Players"]

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
# Edit-match dialog  (defined here so it's available anywhere on the page)
# ---------------------------------------------------------------------------
@st.dialog("✏️ Edit Match — Scores & Awards", width="large")
def _edit_match_dialog(edit_mid: int) -> None:
    """Modal editor for an already-completed match."""
    m_row  = matches_df[matches_df["match_id"] == edit_mid].iloc[0]
    ta_id  = int(m_row["team_a_id"])
    tb_id  = int(m_row["team_b_id"])
    win_id = int(m_row["winner_id"]) if pd.notna(m_row.get("winner_id")) else None
    cur_sa = int(pd.to_numeric(m_row.get("team_a_score", 0), errors="coerce") or 0)
    cur_sb = int(pd.to_numeric(m_row.get("team_b_score", 0), errors="coerce") or 0)

    st.markdown(
        f"**{_tname(ta_id)}** vs **{_tname(tb_id)}** &nbsp;·&nbsp; "
        f"Winner: **{_tname(win_id)}** &nbsp;·&nbsp; "
        f"Round {int(m_row['round'])}, {str(m_row['bracket']).capitalize()}"
    )
    st.caption("Winner cannot be changed here. Scores shown are final values (queen bonus already included).")
    st.markdown("---")

    sc1, sc2 = st.columns(2)
    new_sa = sc1.number_input(
        f"{_tname(ta_id)} score", min_value=0, max_value=24, value=cur_sa,
        key=f"dlg_sa_{edit_mid}",
    )
    new_sb = sc2.number_input(
        f"{_tname(tb_id)} score", min_value=0, max_value=24, value=cur_sb,
        key=f"dlg_sb_{edit_mid}",
    )

    st.markdown("---")
    st.markdown("**Awards**")
    st.caption("Changes here replace all existing award entries for this match.")

    both_ids     = [ta_id, tb_id]
    edit_players = (
        players_df[players_df["team_id"].isin(both_ids)].reset_index(drop=True)
        if not players_df.empty else pd.DataFrame()
    )
    existing_aw = get_match_awards(edit_mid)
    ex_map: dict = {}
    if not existing_aw.empty:
        for _, er in existing_aw.iterrows():
            pid = int(er["player_id"])
            ex_map[pid] = {a: int(er.get(a, 0) or 0) for a in AWARDS}

    edit_award_map: dict = {}
    for tid in both_ids:
        tp = edit_players[edit_players["team_id"] == tid] if not edit_players.empty else pd.DataFrame()
        if tp.empty:
            continue
        members = " & ".join(tp["name"].tolist())
        st.markdown(f"**{_tname(tid)}** — {members}")
        for _, p in tp.iterrows():
            pid = int(p["player_id"])
            st.markdown(f"*{p['name']}*")
            p_aws: dict = {}
            acols = st.columns(len(AWARDS))
            for acol, award in zip(acols, AWARDS):
                p_aws[award] = int(acol.checkbox(
                    AWARD_LABELS[award],
                    value=bool(ex_map.get(pid, {}).get(award, 0)),
                    key=f"dlg_{edit_mid}_{pid}_{award}",
                    help=AWARD_DESCRIPTIONS[award],
                ))
            edit_award_map[pid] = p_aws

    st.markdown("---")
    csave, _ = st.columns([1, 3])
    if auth.is_admin():
        if csave.button("💾 Save Changes", type="primary", width='stretch'):
            try:
                edit_match_result(edit_mid, new_sa, new_sb, edit_award_map)
                st.success("Match updated successfully!")
                st.rerun()
            except (ValueError, RuntimeError) as e:
                st.error(str(e))
    else:
        csave.caption("Admin-only: unlock to save changes.")


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
                sa = row.get("team_a_score", "")
                sb = row.get("team_b_score", "")
                score_str = ""
                if sa != "" and sb != "" and str(sa) != "nan" and str(sb) != "nan":
                    score_str = f" ({int(sa)}–{int(sb)})"
                _mc, _ec = st.columns([10, 1])
                _mc.markdown(
                    f"{icon}&nbsp; <span style='color:#6B7BB0'>{ta} vs {tb}</span>"
                    f" → **{winner}**{score_str}",
                    unsafe_allow_html=True,
                )
                if auth.is_admin() and _ec.button("✎", key=f"edit_btn_{int(row['match_id'])}", help="Edit this match"):
                    _edit_match_dialog(int(row["match_id"]))
            else:
                st.markdown(f"{icon}&nbsp; **{ta}** vs **{tb}**")
    else:
        st.info("No matches scheduled yet.")

# ── RIGHT: Record form ───────────────────────────────────────────────────────
with record_col:
    # ---- Match selector (only scheduled matches) ---------------------------
    scheduled = matches_df[matches_df["status"] == "scheduled"].copy()
    # Normalize datetimes and sort by scheduled date + time so ordering matches Home
    scheduled["_sched_dt"] = pd.to_datetime(scheduled.get("scheduled_date", None), dayfirst=True, errors="coerce")
    scheduled["_sched_dt_time"] = pd.NaT
    if "scheduled_time" in scheduled.columns:
        has_time = scheduled["scheduled_time"].notna() & (scheduled["scheduled_time"].astype(str).str.strip() != "")
        if has_time.any():
            combined = (scheduled.loc[has_time, "scheduled_date"].astype(str).str.strip()
                        + " " + scheduled.loc[has_time, "scheduled_time"].astype(str).str.strip())
            scheduled.loc[has_time, "_sched_dt_time"] = pd.to_datetime(combined, dayfirst=True, errors="coerce")
    scheduled = scheduled.sort_values(["_sched_dt", "_sched_dt_time", "round", "match_id"], na_position="last", kind="mergesort")

    if scheduled.empty:
        finals_rows = matches_df[matches_df["bracket"].str.lower() == "finals"] if not matches_df.empty else pd.DataFrame()
        finals_done = not finals_rows.empty and str(finals_rows.iloc[0]["status"]) == "done"
        if finals_done:
            champion_id = int(finals_rows.iloc[0]["winner_id"])
            st.success(f"🏆 Tournament complete! Champion: **{team_name.get(champion_id, f'Team {champion_id}')}**")
        else:
            st.info("No matches are currently scheduled. Results may still be pending from the current round.")

    else:
        scheduled["label"] = scheduled.apply(
            lambda r: (
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

            st.markdown("---")
            st.markdown("**Match Scores** *(pieces only — Queen bonus added automatically)*")
            score_a = st.number_input(
                f"{_tname(team_a_id)}",
                min_value=0, max_value=24, value=0,
                key=f"score_a_{selected_match_id}",
                help="Piece points for this team. Queen bonus (+5, capped at 24) is applied automatically.",
            )
            score_b = st.number_input(
                f"{_tname(team_b_id)}",
                min_value=0, max_value=24, value=0,
                key=f"score_b_{selected_match_id}",
                help="Piece points for this team. Queen bonus (+5, capped at 24) is applied automatically.",
            )
            st.markdown("---")

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
            if auth.is_admin():
                if st.button("✅ Save Result & Awards", type="primary", width='stretch'):
                    try:
                        record_result(selected_match_id, winner_id, team_a_score=score_a, team_b_score=score_b)
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
            else:
                st.info("Unlock admin to record match results.")


