"""BizCardX - scan business cards, extract contact details with OCR, store them in MySQL."""
import hashlib

import pandas as pd
import streamlit as st

st.set_page_config(page_title="BizCardX", page_icon="📇", layout="wide")

import auth  # noqa: E402  (set_page_config must run first)
import db  # noqa: E402
from card_parser import FIELDS, LABELS, parse_card  # noqa: E402
from ocr_engine import draw_boxes, process_card  # noqa: E402

REGION = st.secrets.get("app", {}).get("default_region", "AE")  # for numbers without +code


def flash(message):
    """Show a message after st.rerun()."""
    st.session_state.flash = message
    st.rerun()


def mask_phone(phones):
    return ", ".join(p[:-6] + "****" + p[-2:] if len(p) > 8 else "****" for p in (phones or "").split(", ") if p)


def mask_email(email):
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return local[0] + "***@" + domain


def contact_form(key, values, button):
    """Editable form for the contact fields. Returns the edited dict or None."""
    with st.form(key):
        edited = {}
        for f in FIELDS:
            if f == "address":
                edited[f] = st.text_area(LABELS[f], values.get(f) or "", key=f"{key}_{f}")
            else:
                edited[f] = st.text_input(LABELS[f], values.get(f) or "", key=f"{key}_{f}")
        if st.form_submit_button(button, type="primary"):
            return {k: v.strip() for k, v in edited.items()}
    return None


# ---------------------------------------------------------------- Scan page
def scan_page(user):
    st.header("Scan a business card")
    upload = st.file_uploader("Upload a card photo (JPG / PNG)", type=["jpg", "jpeg", "png"])
    if not upload:
        return

    file_bytes = upload.getvalue()
    scan_id = hashlib.sha256(file_bytes).hexdigest()[:12]
    # Streamlit re-runs the script on every click: only run OCR once per new image.
    if st.session_state.get("scan_id") != scan_id:
        with st.spinner("Reading the card... (20-40 s on CPU)"):
            try:
                card = process_card(file_bytes)
            except ValueError as e:
                st.error(str(e))
                return
        st.session_state.scan_id = scan_id
        st.session_state.card = card
        st.session_state.parsed = parse_card(card["results"], card["qr"], REGION)
        st.session_state.pop("pending", None)

    card, parsed = st.session_state.card, st.session_state.parsed
    left, right = st.columns(2, gap="large")
    with left:
        st.image(draw_boxes(card["image"], card["results"]), caption="Detected text")
        with st.expander("Raw OCR text"):
            for _, text, conf in card["results"]:
                st.write(f"`{conf:.2f}`  {text}")
            if card["qr"]:
                st.write(f"**QR code:** {card['qr']}")
    with right:
        st.subheader("Review and correct, then save")
        edited = contact_form(f"scan_{scan_id}", parsed, "Save to database")

    if edited:
        if not (edited["full_name"] or edited["email"] or edited["phones"]):
            st.error("Enter at least a name, email or phone.")
            return
        duplicates = db.find_duplicates(edited, card["hash"])
        if not duplicates:
            new_id = db.insert_contact(edited, card["hash"], _raw_text(card), user["id"])
            flash(f"Saved contact #{new_id}.")
        st.session_state.pending = {"data": edited, "duplicates": duplicates}

    if st.session_state.get("pending"):
        resolve_duplicates(card, user)


def _raw_text(card):
    return "\n".join(text for _, text, _ in card["results"])


def resolve_duplicates(card, user):
    pending = st.session_state.pending
    st.warning("This card may already be in the database:")
    st.dataframe(pd.DataFrame(pending["duplicates"]), hide_index=True)
    ids = [d["id"] for d in pending["duplicates"]]
    target = st.selectbox("Existing record", ids, format_func=lambda i: f"#{i}")
    c1, c2, c3 = st.columns(3)
    if c1.button("Update existing record"):
        db.update_contact(target, pending["data"], user["id"])
        st.session_state.pop("pending")
        flash(f"Updated contact #{target}.")
    if c2.button("Save as new anyway"):
        new_id = db.insert_contact(pending["data"], card["hash"], _raw_text(card), user["id"])
        st.session_state.pop("pending")
        flash(f"Saved contact #{new_id}.")
    if c3.button("Cancel"):
        st.session_state.pop("pending")
        st.rerun()


# ------------------------------------------------------------ Contacts page
def contacts_page(user):
    st.header("Contacts")
    search = st.text_input("Search by name, company, designation, email, phone or address")
    rows = db.list_contacts(search.strip())
    if not rows:
        st.info("No contacts found.")
        return

    df = pd.DataFrame(rows)
    if not auth.can(user, "see_full"):
        df["phones"] = df["phones"].map(mask_phone)
        df["email"] = df["email"].map(mask_email)
    st.dataframe(df, hide_index=True)

    if auth.can(user, "export"):
        if st.download_button("Export CSV", df.to_csv(index=False), "contacts.csv", "text/csv"):
            db.log_export(user["id"], len(df))

    if not auth.can(user, "edit"):
        return
    st.divider()
    st.subheader("Edit or delete a contact")
    choice = st.selectbox(
        "Contact", df["id"].tolist(),
        format_func=lambda i: f"#{i} - {df.loc[df['id'] == i, 'full_name'].iloc[0] or '(no name)'}",
    )
    contact = db.get_contact(choice)
    edited = contact_form(f"edit_{choice}", contact, "Update")
    if edited:
        db.update_contact(choice, edited, user["id"])
        flash(f"Updated contact #{choice}.")

    if auth.can(user, "delete"):
        confirm = st.checkbox(f"Yes, permanently delete contact #{choice}")
        if st.button("Delete", disabled=not confirm):
            db.delete_contact(choice, user["id"])
            flash(f"Deleted contact #{choice}.")


def audit_page():
    st.header("Audit log")
    st.dataframe(pd.DataFrame(db.list_audit()), hide_index=True)


# ---------------------------------------------------------------- Main
user = auth.require_login()

st.sidebar.title("📇 BizCardX")
st.sidebar.write(f"Signed in as **{user['username']}** ({user['role']})")
pages = ["Contacts"]
if auth.can(user, "scan"):
    pages.insert(0, "Scan card")
if auth.can(user, "audit"):
    pages.append("Audit log")
page = st.sidebar.radio("Menu", pages)
if st.sidebar.button("Log out"):
    auth.logout()

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

if page == "Scan card":
    scan_page(user)
elif page == "Contacts":
    contacts_page(user)
else:
    audit_page()
    