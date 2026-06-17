"""
auth.py
-------
Very small admin-auth helper for the Streamlit app.

- Uses a single admin password hash stored in `st.secrets["ADMIN_PASSWORD_HASH"]`.
- Adds a reusable sidebar widget to login/logout and exposes `is_admin()`.

This is intentionally simple: if you want per-user identities, use GitHub OAuth
or an external auth provider and check `st.session_state` similarly.
"""

from __future__ import annotations

import hashlib

try:
    import streamlit as st
except Exception:  # pragma: no cover - import-time when not running in Streamlit
    st = None


def _check_password(password: str) -> bool:
    if st is None:
        return False
    try:
        stored = st.secrets.get("ADMIN_PASSWORD_HASH")
    except Exception:
        return False
    if not stored:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == stored


def is_admin() -> bool:
    if st is None:
        return False
    return bool(st.session_state.get("is_admin", False))


def admin_widget() -> None:
    """Render a small login widget in the sidebar to toggle admin mode.

    Stores the boolean `is_admin` in `st.session_state` on success.
    """
    if st is None:
        return

    # Show current state
    if is_admin():
        st.sidebar.success("Admin mode")
        if st.sidebar.button("Log out", key="admin_logout"):
            # Flush any unsaved changes to GitHub before ending admin session
            try:
                from modules.excel_sync import sync_to_github
                sync_to_github()
            except Exception:
                pass
            st.session_state["is_admin"] = False
            st.rerun()
        return

    # Use a text input + button with an on_click callback that reads the
    # value from `st.session_state` to avoid races where the typed value
    # isn't available to the click handler on the same run.
    pw_key = "admin_pw_input"
    err_key = "_admin_invalid"

    # If a previous attempt failed, show the error once then clear it.
    if st.session_state.get(err_key, False):
        st.sidebar.error("Invalid password")
        st.session_state[err_key] = False

    def _unlock_cb() -> None:
        pw_val = st.session_state.get(pw_key, "")
        if _check_password(pw_val):
            st.session_state["is_admin"] = True
            st.session_state[pw_key] = ""
        else:
            st.session_state[err_key] = True

    st.sidebar.text_input("Admin password", type="password", key=pw_key)
    st.sidebar.button("Unlock admin", key="admin_unlock", on_click=_unlock_cb)
