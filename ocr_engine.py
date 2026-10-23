"""Image loading, clean-up, orientation fix, OCR and QR decoding.

Everything happens in memory: the uploaded card is never written to disk.
"""
import cv2
import easyocr
import imagehash
import numpy as np
import streamlit as st
from PIL import Image

MAX_SIDE = 1280   # shrink huge phone photos (speed + memory on the cloud)
MIN_SIDE = 1000   # enlarge tiny scans (small text is hard to read)
PROBE_SIDE = 640  # small copy used only to guess the orientation

ROTATIONS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


@st.cache_resource(show_spinner="Loading OCR model (first run downloads ~100 MB)...")
def get_reader():
    # Loaded once per server process, not on every click.
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def load_image(file_bytes):
    img = cv2.imdecode(np.frombuffer(file_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read the image. Please upload a JPG or PNG file.")
    return img


def resize(img, max_side=MAX_SIDE, min_side=MIN_SIDE):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / longest
    elif longest < min_side:
        scale = min_side / longest
    else:
        return img
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)


def enhance(img):
    """Grayscale + local contrast boost (CLAHE) so faint text stands out."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def rotate(img, angle):
    code = ROTATIONS[angle]
    return img if code is None else cv2.rotate(img, code)


def _score(results):
    # More confidently-read characters = more likely the correct orientation.
    return sum(conf * len(text) for _, text, conf in results if conf > 0.2)


def best_orientation(img):
    """Try the likely rotations on a small copy and keep the best one."""
    reader = get_reader()
    h, w = img.shape[:2]
    probe = resize(img, max_side=PROBE_SIDE, min_side=PROBE_SIDE)
    # A portrait photo of a landscape card is usually turned 90 or 270 degrees.
    angles = [0, 180] if w >= h else [90, 270]
    scores = {a: _score(reader.readtext(enhance(rotate(probe, a)))) for a in angles}
    if w < h and max(scores.values()) < 40:  # weak result: maybe a vertical card
        scores[0] = _score(reader.readtext(enhance(probe)))
    return max(scores, key=scores.get)


def decode_qr(img):
    try:
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    except cv2.error:
        return ""
    return data or ""


def image_hash(img):
    """Perceptual hash: near-identical images give near-identical hashes."""
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return str(imagehash.phash(Image.fromarray(rgb)))


def process_card(file_bytes):
    img = resize(load_image(file_bytes))
    img = rotate(img, best_orientation(img))
    results = get_reader().readtext(enhance(img))
    return {
        "image": img,
        "results": results,       # list of (bounding_box, text, confidence)
        "qr": decode_qr(img),
        "hash": image_hash(img),
    }


def draw_boxes(img, results):
    out = img.copy()
    for bbox, _, _ in results:
        pts = np.array(bbox, dtype=np.int32)
        cv2.polylines(out, [pts], True, (0, 200, 0), 2)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)