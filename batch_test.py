"""Run the OCR pipeline on a folder of card images (no database, no UI).

Usage:
  python batch_test.py <images_folder>                      -> writes results.csv
  python batch_test.py <images_folder> ground_truth.csv     -> also prints accuracy

ground_truth.csv columns: file, full_name, designation, company, phones, email, website
"""
import csv
import re
import sys
import time
from pathlib import Path

from card_parser import FIELDS, parse_card
from ocr_engine import process_card

COMPARE = ["full_name", "designation", "company", "phones", "email", "website"]


def norm(value):
    return re.sub(r"[^a-z0-9+]", "", (value or "").lower())


def same(field, got, want):
    if field == "phones":  # correct if every expected number was found
        want_set = {norm(p) for p in want.split(",") if p.strip()}
        return want_set <= {norm(p) for p in got.split(",")}
    return norm(got) == norm(want)


def main():
    folder = Path(sys.argv[1])
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    rows = []
    for path in images:
        start = time.time()
        card = process_card(path.read_bytes())
        data = parse_card(card["results"], card["qr"])
        rows.append({"file": path.name, **data})
        print(f"{path.name}: {time.time() - start:.1f}s  {data['full_name']} | {data['email']}")

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", *FIELDS])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote results.csv ({len(rows)} cards)")

    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            truth = {r["file"]: r for r in csv.DictReader(f)}
        print("\nField accuracy:")
        for field in COMPARE:
            checked = [r for r in rows if r["file"] in truth and truth[r["file"]].get(field)]
            correct = sum(same(field, r[field], truth[r["file"]][field]) for r in checked)
            if checked:
                print(f"  {field:12} {correct}/{len(checked)}  ({100 * correct / len(checked):.0f}%)")


if __name__ == "__main__":
    main()