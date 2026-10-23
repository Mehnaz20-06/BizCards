"""Turns raw OCR output into structured contact fields."""
import re

import phonenumbers
from rapidfuzz import fuzz

FIELDS = ["full_name", "designation", "company", "phones", "email", "website", "address"]
LABELS = {
    "full_name": "Name",
    "designation": "Designation",
    "company": "Company",
    "phones": "Phone(s)",
    "email": "Email",
    "website": "Website",
    "address": "Address",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
TLDS = r"com|net|org|info|biz|io|co|ae|kr|in|uk|sa|pk|sg|my|us|qa|om|bh|kw"
WEB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:" + TLDS + r")\b(?:/[^\s,]*)?",
    re.I,
)

TITLE_WORDS = {
    "manager", "director", "executive", "engineer", "officer", "ceo", "cto", "cfo", "coo",
    "founder", "cofounder", "president", "vp", "head", "lead", "consultant", "developer",
    "analyst", "specialist", "supervisor", "coordinator", "assistant", "partner", "owner",
    "architect", "designer", "administrator", "accountant", "technician", "representative",
    "associate", "chairman", "intern", "dept", "department", "sales", "marketing", "advisor",
    "scientist", "professor", "doctor", "dr", "agent", "secretary", "trainee", "principal",
    "chairwoman", "chairperson", "chair", "md", "gm", "managing", "general", "vice",
    "controller", "auditor", "surveyor", "broker", "attorney", "lawyer", "advocate",
    "physician", "pharmacist", "editor", "buyer", "planner", "strategist", "recruiter",
}
CREDENTIALS = {
    "frics", "mrics", "rics", "mba", "phd", "cpa", "pmp", "acca", "cfa", "cma", "ca",
    "pe", "msc", "bsc", "btech", "mtech", "llb", "fcca", "aca", "fca",
}
COMPANY_WORDS = {
    "ltd", "llc", "inc", "pvt", "corp", "corporation", "company", "co", "gmbh", "plc",
    "fze", "fzco", "fzc", "limited", "group", "llp", "sdn", "bhd", "est", "establishment",
}
BUSINESS_WORDS = {
    "advertising", "printing", "service", "services", "solutions", "technologies",
    "technology", "trading", "industries", "enterprises", "consulting", "international",
}
ADDRESS_WORDS = {
    "road", "rd", "street", "st", "avenue", "ave", "floor", "fl", "building", "bldg", "tower",
    "block", "sector", "suite", "office", "box", "near", "opp", "roundabout", "district",
    "city", "dong", "gu", "ro", "gil", "si", "do", "eup", "uae", "dubai", "sharjah",
    "abu", "dhabi", "korea", "seoul", "india", "republic", "nagar", "lane", "area", "zone",
    "industrial", "plot", "po", "village", "state", "province", "center", "centre",
}
FREE_MAIL = {"gmail", "yahoo", "outlook", "hotmail", "icloud", "live", "aol", "proton", "protonmail"}


def _words(text):
    return re.findall(r"[a-z]+", text.lower())


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _fix_contact_text(text):
    """Repair common OCR slips in emails/websites:
    'www i-aha com' -> 'www.i-aha.com',  'Ejhchoi@ahatouchcom' -> 'jhchoi@ahatouch.com'."""
    if "@" in text or "www" in text.lower():
        text = re.sub(r"\s*\.\s*(?=[A-Za-z])", ".", text)
    text = re.sub(r"(?i)\bwww[\s,;:]+", "www.", text)
    # OCR turned the dot inside an email into a space: 'Mail: sinimol noushad@...'
    text = re.sub(r"(?i)(\b(?:e-?mail|ma[il1]{1,3})\s*[:.]?\s*[a-z0-9._-]+)\s(?=[a-z0-9._-]+@)", r"\1.", text)
    # a website line where 'www.' was misread and the TLD is spaced: '(M UNIQueSolutions coM'
    site = re.fullmatch(r"(?i)\W*(?:\S{1,3}\s+)?(?:w{2,3}\W*)?([a-z0-9-]{5,})[\s,.]+(com|net|org|info|biz|io)\W*",
                        text.strip())
    if site and "@" not in text:
        text = f"www.{site.group(1)}.{site.group(2)}"
    # missing dot before the TLD, with or without a space: 'ahatouch com' / 'ahatouchcom'
    text = re.sub(r"(?i)((?:@|www\.)[A-Za-z0-9-]+?)[\s,;]*(" + TLDS + r")(?![\w.-])", r"\1.\2", text)
    # a card label glued to an all-lowercase email: 'Ejhchoi@...' / 'E-mail:jhchoi@...'
    text = re.sub(r"(?:\b|(?<=\d))(?:E-?mail:?|Mail:?|E:?)\s*(?=[a-z0-9._%+-]+@)", " ", text)
    return text


def _fix_address(text):
    """'Floor |, At Fattan' -> 'Floor 1, At Fattan';  'Umm Ramool_Dubai' -> 'Umm Ramool Dubai'."""
    text = re.sub(r"(?<=\s)\|(?=[\s,])", "1", text)
    return text.replace("_", " ")


def _clean(text):
    """OCR often reads commas as semicolons; tidy the ends."""
    return re.sub(r"\s*;\s*", ", ", text).strip(" ,;:|'\"")


PHONE_SPAN = re.compile(r"\+\s*[\dOoIlTS]{1,3}[\s\d()\[\]|OoIlSsJjBTZ.,-]{6,}")
OCR_DIGITS = str.maketrans("OoIlSsBTZ", "001155872")


def _fix_phone_text(text):
    """'+971 (0JS5 574 6535' -> '+971 55 574 6535'."""
    def repair(match):
        span = match.group()
        # '(0)' trunk prefix after the country code is not dialled internationally;
        # OCR often reads its ')' as J, 1 or ].
        span = re.sub(r"\(\s*[0Oo]\s*[)\]Jj1lI|]?", " ", span)
        # letters that look like digits, only when they sit between digits
        return re.sub(r"(?<=[\d\s+])[OoIlSsBTZ](?=[\s]*\d)", lambda m: m.group().translate(OCR_DIGITS), span)
    return PHONE_SPAN.sub(repair, text)


def find_phones(text, region):
    text = _fix_phone_text(text)
    # '+971,55 754.6710' -> '+971 55 754 6710'
    text = re.sub(r"(?<=\d)[,.;](?=\s?\d)", " ", text)
    phones = []
    for match in phonenumbers.PhoneNumberMatcher(text, region):
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in phones:
            phones.append(e164)
    return phones


def _strip_credentials(text):
    """'SINIMOL NOUSHAD | FRICS' -> 'SINIMOL NOUSHAD' (OCR may read '|' as 'I')."""
    text = re.split(r"\s*[|,]\s*", text)[0]
    words = text.split()
    while len(words) > 1 and (_norm(words[-1]) in CREDENTIALS or words[-1] in {"I", "l", "|"}):
        words.pop()
    return " ".join(words)


def _repair_website(site, company):
    """Use the company name (read separately on the card) to repair the website:
    'www.mmuniqueprolectsolutions.com' + 'UniQue Project Solutions'
    -> 'www.uniqueprojectsolutions.com'."""
    company_key = _norm(company)
    if not site or "://" in site or len(company_key) < 4:
        return site
    host = site[4:] if site.startswith("www.") else site
    label, dot, rest = host.partition(".")
    pos = label.find(company_key[:4])
    if 0 < pos <= 3:  # junk in front, from a misread 'www.'
        label = label[pos:]
    if len(label) == len(company_key) and fuzz.ratio(label, company_key) >= 90:
        label = company_key  # same length, 1-2 misread letters: trust the company line
    return "www." + label + dot + rest


def _domain_label(address):
    """'jhchoi@ahatouch.com' -> 'ahatouch',  'www.i-aha.com' -> 'iaha'."""
    host = address.split("@")[-1].lower()
    host = re.sub(r"^(https?://)?(www\.)?", "", host).split("/")[0]
    return _norm(host.split(".")[0])


def _lines(results):
    lines = []
    for bbox, text, conf in results:
        text = text.strip()
        if len(text) < 2:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        lines.append({
            "text": text, "conf": conf,
            "top": min(ys), "bottom": max(ys), "left": min(xs), "right": max(xs),
            "height": max(ys) - min(ys),
        })
    lines.sort(key=lambda l: (round(l["top"] / 15), l["left"]))
    return lines


def parse_qr(qr_text, region):
    """Business-card QR codes often hold a vCard or a WhatsApp link; their data is exact."""
    out = {}
    if not qr_text:
        return out
    upper = qr_text.upper()
    if upper.startswith("BEGIN:VCARD"):
        for raw in qr_text.splitlines():
            if ":" not in raw:
                continue
            key, val = raw.split(":", 1)
            key, val = key.split(";")[0].upper(), val.strip()
            if not val:
                continue
            if key == "FN":
                out["full_name"] = val
            elif key == "ORG":
                out["company"] = val.replace(";", " ").strip()
            elif key == "TITLE":
                out["designation"] = val
            elif key == "EMAIL":
                out.setdefault("email", val.lower())
            elif key == "URL":
                out.setdefault("website", val)
            elif key == "ADR":
                out["address"] = ", ".join(p for p in val.split(";") if p.strip())
            elif key == "TEL":
                out.setdefault("phones", []).extend(find_phones(val, region))
    else:
        wa = re.search(r"(?:wa\.me/|phone=)\+?(\d{7,15})", qr_text)
        if wa:
            out["phones"] = find_phones("+" + wa.group(1), region)
        elif qr_text.lower().startswith(("http://", "https://")) and "wa.me" not in qr_text:
            out["qr_url"] = qr_text
    return out


def parse_card(results, qr_text="", region="AE"):
    lines = _lines(results)
    emails, websites, phones = [], [], []
    used = set()

    # 1. Reliable fields first: email, website, phone (pattern based).
    for i, line in enumerate(lines):
        text = _fix_contact_text(line["text"])
        found = False
        for e in EMAIL_RE.findall(text):
            emails.append(e.lower().strip("."))
            found = True
        rest = EMAIL_RE.sub(" ", text)
        for w in WEB_RE.findall(rest):
            websites.append(w.lower().strip("."))
            found = True
        p = find_phones(rest, region)
        if p:
            phones += [x for x in p if x not in phones]
            found = True
        if found:
            used.add(i)
    if not phones:
        phones = find_phones(" ".join(l["text"] for l in lines), region)

    domains = {_domain_label(a) for a in emails + websites}
    domains = {d for d in domains if len(d) >= 3 and d not in FREE_MAIL}

    def matches_domain(text):
        n = _norm(text)
        return len(n) >= 3 and any(n in d or fuzz.partial_ratio(n, d) >= 85 for d in domains)

    remaining = [i for i in range(len(lines)) if i not in used]

    # 2. Designation: first line containing a job-title word.
    title_i = next(
        (i for i in remaining
         if set(_words(lines[i]["text"])) & TITLE_WORDS and not re.search(r"\d", lines[i]["text"])),
        None,
    )

    # 3. Company: legal suffix > matches email/website domain > the domain itself.
    company_i = next(
        (i for i in remaining if i != title_i and set(_words(lines[i]["text"])) & COMPANY_WORDS),
        None,
    )
    if company_i is None:
        company_i = next((i for i in remaining if i != title_i and matches_domain(lines[i]["text"])), None)
    if company_i is None:  # e.g. 'UniQue Project Solutions'
        company_i = next(
            (i for i in remaining
             if i != title_i and set(_words(lines[i]["text"])) & BUSINESS_WORDS and lines[i]["conf"] >= 0.3),
            None,
        )
    company = lines[company_i]["text"] if company_i is not None else ""
    if not company and domains:
        company = sorted(domains)[0].title()

    # 4. Name: a short letters-only line, ideally just above the designation.
    def is_name_like(i):
        text = _strip_credentials(lines[i]["text"])
        words = _words(text)
        return (
            i not in (title_i, company_i)
            and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,39}", text)
            and 1 <= len(text.split()) <= 4
            and not set(words) & (TITLE_WORDS | COMPANY_WORDS | BUSINESS_WORDS | ADDRESS_WORDS)
            and not matches_domain(text)
        )

    candidates = [i for i in remaining if is_name_like(i)]
    name_i = None
    if title_i is not None:
        t = lines[title_i]
        above = [
            i for i in candidates
            if lines[i]["bottom"] <= t["top"] + 0.5 * t["height"]
            and lines[i]["left"] < t["right"] and lines[i]["right"] > t["left"]  # same column
        ]
        if above:
            name_i = min(above, key=lambda i: t["top"] - lines[i]["bottom"])
    if name_i is None and candidates:
        name_i = max(candidates, key=lambda i: lines[i]["height"])  # biggest font

    # 5. Address: what is left that looks like an address.
    taken = {title_i, company_i, name_i}
    leftover = [
        i for i in remaining
        if i not in taken and lines[i]["conf"] >= 0.2
        and not matches_domain(lines[i]["text"])
        and not set(_words(lines[i]["text"])) & BUSINESS_WORDS  # logo / tagline
    ]
    hinted = [
        i for i in leftover
        if re.search(r"\d", lines[i]["text"]) or set(_words(lines[i]["text"])) & ADDRESS_WORDS
    ]

    def next_to_address(i):
        # a line with no hint ('Al Nakheel', 'Umm Ramool Dubai') counts if it sits
        # directly above/below an address line in the same column
        a = lines[i]
        return any(
            abs(a["top"] - lines[h]["top"]) <= 1.8 * max(a["height"], lines[h]["height"])
            and a["left"] < lines[h]["right"] and a["right"] > lines[h]["left"]
            for h in hinted
        )

    address_parts = [lines[i]["text"] for i in leftover if i in hinted or next_to_address(i)]
    full_name = _strip_credentials(lines[name_i]["text"]) if name_i is not None else ""
    if full_name.isupper():
        full_name = full_name.title()  # 'SINIMOL NOUSHAD' -> 'Sinimol Noushad'

    data = {
        "full_name": _clean(full_name),
        "designation": _clean(lines[title_i]["text"]) if title_i is not None else "",
        "company": _clean(company),
        "phones": phones,
        "email": emails[0] if emails else "",
        "website": _repair_website(websites[0], company) if websites else "",
        "address": ", ".join(_clean(_fix_address(a)) for a in address_parts),
    }

    # 6. QR data is exact, so it wins over OCR guesses.
    qr = parse_qr(qr_text, region)
    for key in ("full_name", "designation", "company", "email", "address"):
        if qr.get(key):
            data[key] = qr[key]
    if qr.get("website") or (not data["website"] and qr.get("qr_url")):
        data["website"] = qr.get("website") or qr["qr_url"]
    data["phones"] = ", ".join(dict.fromkeys(data["phones"] + qr.get("phones", [])))
    return data