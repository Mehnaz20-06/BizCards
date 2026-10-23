"""Create an app login from the terminal.

Usage:  python create_user.py <username> <admin|editor|viewer> [secrets_file]
"""
import getpass
import sys
import tomllib

import bcrypt
import mysql.connector


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[2] not in ("admin", "editor", "viewer"):
        sys.exit("Usage: python create_user.py <username> <admin|editor|viewer> [secrets_file]")
    username, role = sys.argv[1], sys.argv[2]
    secrets_file = sys.argv[3] if len(sys.argv) == 4 else ".streamlit/secrets.toml"

    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("Password too short.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")

    with open(secrets_file, "rb") as f:
        cfg = tomllib.load(f)["mysql"]
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, password_hash, role),
    )
    conn.commit()
    conn.close()
    print(f"User '{username}' created with role '{role}'.")


if __name__ == "__main__":
    main()
    