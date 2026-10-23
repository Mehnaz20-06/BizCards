"""Login, logout, idle timeout and role checks."""
import time

import bcrypt
import streamlit as st

import db

IDLE_TIMEOUT = 30 * 60  # seconds
MAX_ATTEMPTS = 5


def logout():
    st.session_state.clear()
    st.rerun()


def require_login():
    """Show the login form and stop the page until a valid user is signed in."""
    user = st.session_state.get("user")
    if user:
        if time.time() - st.session_state.get("last_seen", 0) > IDLE_TIMEOUT:
            st.session_state.clear()
            st.warning("Session expired. Please log in again.")
        else:
            st.session_state.last_seen = time.time()
            return user

    st.title("BizCardX - Sign in")
    attempts = st.session_state.get("attempts", 0)
    if attempts >= MAX_ATTEMPTS:
        st.error("Too many failed attempts. Reload the page later.")
        st.stop()

    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        row = db.get_user(username.strip())
        if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            st.session_state.user = {"id": row["id"], "username": row["username"], "role": row["role"]}
            st.session_state.last_seen = time.time()
            st.session_state.attempts = 0
            db.record_login(row["id"])
            st.rerun()
        st.session_state.attempts = attempts + 1
        time.sleep(1)  # slows down password guessing
        st.error("Invalid username or password.")
    st.stop()


def can(user, action):
    allowed = {
        "scan": {"admin", "editor"},
        "edit": {"admin", "editor"},
        "delete": {"admin"},
        "export": {"admin"},
        "audit": {"admin"},
        "see_full": {"admin", "editor"},  # viewers see masked phone/email
    }
    return user["role"] in allowed[action]
