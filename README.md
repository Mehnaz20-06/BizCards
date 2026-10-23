# BizCardX – Secure Business Card OCR

Upload a photo of a business card; the app extracts name, designation, company,
phone numbers, email, website and address with OCR, lets you review them, checks
for duplicates and stores the contact in MySQL.

## Features
- Automatic orientation fix + image enhancement (OpenCV)
- Text recognition with EasyOCR (runs locally, no third-party OCR API)
- Field extraction with regex, Google phonenumbers, QR/vCard decoding and layout rules
- Duplicate detection (email, phone, fuzzy name + company, perceptual image hash)
- Login with bcrypt-hashed passwords and roles (admin / editor / viewer)
- Masked phone/email for viewers, audit log of every action
- Parameterized SQL queries, credentials kept outside the code

## Tech stack
Python 3.11 · Streamlit · OpenCV · EasyOCR (PyTorch) · phonenumbers · rapidfuzz · imagehash · MySQL 8

## Run locally
    pip install -r requirements.txt
    # create the database: run schema.sql in MySQL
    # add DB credentials to .streamlit/secrets.toml
    python create_user.py admin admin
    streamlit run app.py