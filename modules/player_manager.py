"""
player_manager.py  —  Phase 2
Handles adding, editing, and listing players with skill ratings.
"""

import pandas as pd
from modules.excel_sync import load_sheet, save_sheet, get_next_id


def add_player(name: str, skill_rating: float) -> int:
    """
    Add a new player to the Players sheet.
    Returns the new player_id.
    """
    name = name.strip()
    if not name:
        raise ValueError("Player name cannot be empty.")
    if not (1.0 <= skill_rating <= 10.0):
        raise ValueError("Skill rating must be between 1 and 10.")

    df = load_sheet("Players")

    # Prevent duplicate names (case-insensitive)
    if not df.empty and name.lower() in df["name"].str.lower().values:
        raise ValueError(f'A player named "{name}" already exists.')

    new_id = get_next_id("Players", "player_id")
    new_row = pd.DataFrame([{
        "player_id":    new_id,
        "name":         name,
        "skill_rating": round(float(skill_rating), 1),
        "team_id":      None,
    }])
    if df.empty:
        df = new_row
    else:
        df = pd.concat([df, new_row], ignore_index=True)
    save_sheet("Players", df)
    return new_id


def get_all_players() -> pd.DataFrame:
    """Return all players as a DataFrame."""
    return load_sheet("Players")


def delete_player(player_id: int) -> None:
    """
    Remove a player by ID.
    Only allowed when no teams have been formed yet.
    """
    teams_df = load_sheet("Teams")
    if not teams_df.empty:
        raise RuntimeError("Cannot delete players after teams have been formed.")

    df = load_sheet("Players")
    if df.empty or player_id not in df["player_id"].values:
        raise ValueError(f"Player ID {player_id} not found.")

    df = df[df["player_id"] != player_id].reset_index(drop=True)
    save_sheet("Players", df)


def update_player_team(player_id: int, team_id: int) -> None:
    """Assign a player to a team (called by team_builder)."""
    df = load_sheet("Players")
    if df.empty or player_id not in df["player_id"].values:
        raise ValueError(f"Player ID {player_id} not found.")
    df.loc[df["player_id"] == player_id, "team_id"] = team_id
    save_sheet("Players", df)
