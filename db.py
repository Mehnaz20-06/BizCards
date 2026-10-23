"""All database access lives here.

Every query uses %s placeholders (parameterized), so user input can never
change the SQL itself -> no SQL injection.
"""
from contextlib import contextmanager

import imagehash
import mysql.connector
import streamlit as st
from rapidfuzz import fuzz

from card_parser import FIELDS


@contextmanager
def get_cursor(commit=False):
    # Credentials come from .streamlit/secrets.toml (local) or the Streamlit Cloud
    # "Secrets" box, never from the code.
    conn = mysql.connector.connect(**st.secrets["mysql"])
    try:
        cur = conn.cursor(dictionary=True)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def log_action(cur, user_id, action, contact_id=None, details=""):
    cur.execute(
        "INSERT INTO audit_log (user_id, action, contact_id, details) VALUES (%s, %s, %s, %s)",
        (user_id, action, contact_id, (details or "")[:255]),
    )


def get_user(username):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = %s",
            (username,),
        )
        return cur.fetchone()


def record_login(user_id):
    with get_cursor(commit=True) as cur:
        log_action(cur, user_id, "LOGIN")


def _values(data):
    return [data.get(f) or None for f in FIELDS]  # empty string -> NULL


def insert_contact(data, image_hash, raw_text, user_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO contacts
               (full_name, designation, company, phones, email, website, address,
                raw_text, image_hash, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (*_values(data), raw_text, image_hash, user_id),
        )
        new_id = cur.lastrowid
        log_action(cur, user_id, "CREATE", new_id, data.get("full_name"))
        return new_id


def update_contact(contact_id, data, user_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE contacts SET full_name=%s, designation=%s, company=%s, phones=%s,
               email=%s, website=%s, address=%s WHERE id=%s""",
            (*_values(data), contact_id),
        )
        log_action(cur, user_id, "UPDATE", contact_id, data.get("full_name"))


def delete_contact(contact_id, user_id):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
        log_action(cur, user_id, "DELETE", contact_id)


def get_contact(contact_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        return cur.fetchone()


def list_contacts(search=""):
    sql = ("SELECT id, full_name, designation, company, phones, email, website, address, created_at "
           "FROM contacts")
    params = ()
    if search:
        like = f"%{search}%"
        sql += (" WHERE full_name LIKE %s OR company LIKE %s OR designation LIKE %s"
                " OR email LIKE %s OR phones LIKE %s OR address LIKE %s")
        params = (like,) * 6
    sql += " ORDER BY created_at DESC"
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def log_export(user_id, count):
    with get_cursor(commit=True) as cur:
        log_action(cur, user_id, "EXPORT", details=f"{count} contacts")


def list_audit(limit=500):
    with get_cursor() as cur:
        cur.execute(
            """SELECT a.at, u.username, a.action, a.contact_id, a.details
               FROM audit_log a JOIN users u ON u.id = a.user_id
               ORDER BY a.at DESC LIMIT %s""",
            (limit,),
        )
        return cur.fetchall()


def _split_phones(phones):
    return {p.strip() for p in (phones or "").split(",") if p.strip()}


def _similar(a, b):
    """0-100. Handles word order ('Choi Junghoon') and spacing ('Jung hoon')."""
    return max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", "")))


def find_duplicates(data, image_hash):
    """Return existing contacts that look like the same person, with the reason."""
    with get_cursor() as cur:
        cur.execute("SELECT id, full_name, company, email, phones, image_hash FROM contacts")
        rows = cur.fetchall()

    email = (data.get("email") or "").lower()
    phones = _split_phones(data.get("phones"))
    name = (data.get("full_name") or "").lower()
    company = (data.get("company") or "").lower()
    new_hash = imagehash.hex_to_hash(image_hash) if image_hash else None

    matches = []
    for row in rows:
        reasons = []
        if new_hash is not None and row["image_hash"]:
            if new_hash - imagehash.hex_to_hash(row["image_hash"]) <= 6:  # bits that differ
                reasons.append("same card image")
        if email and (row["email"] or "").lower() == email:
            reasons.append("same email")
        if phones & _split_phones(row["phones"]):
            reasons.append("same phone")
        if name and row["full_name"] and _similar(name, row["full_name"].lower()) >= 85:
            if not company or not row["company"] or _similar(company, row["company"].lower()) >= 70:
                reasons.append("similar name + company")
        if reasons:
            row.pop("image_hash")
            matches.append({**row, "reasons": ", ".join(reasons)})
    return matches