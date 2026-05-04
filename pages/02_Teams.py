"""
02_Teams.py  —  Phase 2
View balanced team pairings and assign custom team names.
"""

import streamlit as st
from modules.excel_sync import load_sheet
from modules.team_builder import build_balanced_teams, rename_team, reset_teams, get_team_players
from modules.ui_helpers import render_logo, get_cmaps, render_df

st.set_page_config(page_title="Teams · Carrom Tournament", page_icon="🤝", layout="wide", initial_sidebar_state="expanded")
render_logo()

st.title("🤝 Teams")
st.caption("Auto-balanced 2v2 teams based on skill ratings. Rename teams after building.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load current state
# ---------------------------------------------------------------------------
players_df  = load_sheet("Players")
teams_df    = load_sheet("Teams")
matches_df  = load_sheet("Matches")

teams_exist    = not teams_df.empty
matches_exist  = not matches_df.empty
n_players      = len(players_df)

# ---------------------------------------------------------------------------
# Build Teams section
# ---------------------------------------------------------------------------
if not teams_exist:
    st.subheader("Build Balanced Teams")

    if n_players < 4:
        st.warning(f"Only {n_players} player(s) registered. Head to **Players** and add at least 4.")
    elif n_players % 2 != 0:
        st.warning(
            f"{n_players} players registered — need an **even** number for 2v2. "
            "Head to **Players** to add one more."
        )
    else:
        # Preview the pairing before confirming
        sorted_p = (
            players_df
            .sort_values("skill_rating", ascending=False)
            .reset_index(drop=True)
        )
        n = len(sorted_p)
        preview_rows = []
        for i in range(n // 2):
            p1 = sorted_p.iloc[i]
            p2 = sorted_p.iloc[n - 1 - i]
            avg = round((float(p1["skill_rating"]) + float(p2["skill_rating"])) / 2, 2)
            preview_rows.append({
                "Team":        f"Team {chr(65 + i)}",
                "Player 1":    p1["name"],
                "Skill 1":     p1["skill_rating"],
                "Player 2":    p2["name"],
                "Skill 2":     p2["skill_rating"],
                "Avg Skill":   avg,
            })

        import pandas as pd
        preview_df = pd.DataFrame(preview_rows)
        st.markdown("**Preview — balanced pairings:**")
        render_df(
            preview_df.style.background_gradient(subset=["Avg Skill"], cmap=get_cmaps()["skill"], vmin=1, vmax=10),
        )

        skill_spread = round(preview_df["Avg Skill"].max() - preview_df["Avg Skill"].min(), 2)
        st.caption(f"Average skill spread across all teams: **{skill_spread}** points")

        if st.button("✅ Confirm & Build Teams", type="primary", use_container_width=True):
            try:
                build_balanced_teams()
                st.success(f"Built **{n // 2} balanced teams** successfully!")
                st.rerun()
            except (RuntimeError, ValueError) as e:
                st.error(str(e))

else:
    # ---------------------------------------------------------------------------
    # Teams are built — show roster cards + rename controls
    # ---------------------------------------------------------------------------
    st.subheader(f"Teams — {len(teams_df)} formed")

    for _, team in teams_df.iterrows():
        team_id   = int(team["team_id"])
        team_name = team["team_name"]
        avg_skill = team["avg_skill"]
        wins      = int(team.get("wins", 0))
        losses    = int(team.get("losses", 0))
        is_elim   = bool(team.get("is_eliminated", False))

        status_badge = "❌ Eliminated" if is_elim else "✅ Active"
        with st.expander(f"**{team_name}**  ·  Avg Skill {avg_skill}  ·  W {wins} / L {losses}  ·  {status_badge}", expanded=True):
            # Players in this team
            team_players = get_team_players(team_id)
            if not team_players.empty:
                cols = st.columns(2)
                for idx, (_, p) in enumerate(team_players.iterrows()):
                    cols[idx % 2].metric(
                        label=f"Player {idx + 1}",
                        value=p["name"],
                        delta=f"Skill {p['skill_rating']}",
                    )
            else:
                st.caption("No players assigned.")

            # Rename form (locked once matches are scheduled)
            if not matches_exist:
                with st.form(f"rename_{team_id}"):
                    new_name = st.text_input("Rename team", value=team_name, max_chars=40)
                    if st.form_submit_button("💾 Save Name"):
                        try:
                            rename_team(team_id, new_name)
                            st.success(f"Renamed to **{new_name}**.")
                            st.rerun()
                        except (ValueError, RuntimeError) as e:
                            st.error(str(e))
            else:
                st.caption("Team names are locked after the schedule is generated.")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Reset (only before matches are scheduled)
    # ---------------------------------------------------------------------------
    if not matches_exist:
        with st.expander("⚠️ Reset Teams"):
            st.warning("This will wipe all teams and clear player assignments. Player list is kept.")
            if st.button("🔄 Reset Teams", type="secondary"):
                try:
                    reset_teams()
                    st.success("Teams reset. Head to Players to adjust the list, then rebuild.")
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
    else:
        st.info("Matches are scheduled — teams are locked. Go to **Schedule** to manage matches.")

