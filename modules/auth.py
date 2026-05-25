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
    stored = st.secrets.get("ADMIN_PASSWORD_HASH")
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
            st.session_state["is_admin"] = False
            st.experimental_rerun()
        return

    pw = st.sidebar.text_input("Admin password", type="password", key="_admin_pw_input")
    if st.sidebar.button("Unlock admin", key="admin_unlock"):
        if _check_password(pw):
            # Mark session as admin and clear the password input to avoid
            # accidental re-submission. Rerun so the sidebar immediately
            # shows the logout button in the refreshed UI.
            st.session_state["is_admin"] = True
            try:
                st.session_state["_admin_pw_input"] = ""
            except Exception:
                pass
            st.experimental_rerun()
        else:
            st.sidebar.error("Invalid password")
