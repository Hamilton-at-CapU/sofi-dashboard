import re
from pathlib import Path

import pandas as pd
import pdfplumber

YEAR = 2024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_amount(raw: str) -> int | None:
    """Parse a dollar amount string, tolerating OCR spaces inside numbers."""
    if not raw:
        return None
    s = raw.strip().lstrip("$").strip()
    if s in ("-", "\u2010", "\u2013", "~", "*", ""):
        return 0
    # Collapse OCR spaces inside numbers: "1 48,633" -> "148,633", "9 ,645" -> "9,645"
    s = re.sub(r"(\d)\s+(\d)", r"\1\2", s)
    s = re.sub(r"(\d)\s+,", r"\1,", s)
    s = re.sub(r"[$,\s]", "", s)
    try:
        return round(float(s))
    except ValueError:
        return None



def is_valid_name(name: str) -> bool:
    """
    Reject sentence fragments masquerading as names.
    A valid name:
      - is not too long (< 50 chars)
      - contains only name-like characters (no lowercase run of 4+ words)
      - does not contain common sentence words
    """
    if len(name) > 50:
        return False
    if re.search(r"\b(that|the|for|been|since|exceeds|reporting|threshold|remuneration is)\b", name, re.IGNORECASE):
        return False
    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", name):
        return False
    return True


def normalise_position(raw: str) -> str | None:
    """Return 'Mayor' or 'Councillor', or None if unrecognised."""
    r = raw.strip().lower()
    # Exact mayor match only — 'Deputy Mayor' must NOT become 'Mayor'
    if r in ("mayor", "city mayor"):
        return "Mayor"
    if any(w in r for w in ("councillor", "councilor", "council member",
                             "city councillor", "council", "deputy mayor",
                             "alderman", "reeve")):
        return "Councillor"
    return None


# ---------------------------------------------------------------------------
# Page-level parsers
# ---------------------------------------------------------------------------

# Number token: must be 3+ digits OR contain a comma (avoids single-digit OCR artifacts)
_NUM = r"\$?\s*(?:\d[\d,]*,\d{3}|\d{3,})(?:\.\d+)?"

STANDARD_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-\(\)][\w\u00C0-\u024F',\.\-\(\)\ ]+?)"   # name (lazy, no newlines, allows parentheses)
    r"\ +"
    r"(City Mayor|City Councillor|Mayor|Deputy Mayor|Councillors?|Councilors?|Council\b|Reeve|Alderman)"  # position
    r"\ +"
    r"(" + _NUM + r")"
    r"(?:\ +(" + _NUM + r"|-))?" ,
    re.MULTILINE | re.IGNORECASE,
)

# Prince George: 6-column format with Councilor spelling and OCR spaces
# "Yu, Simon  Mayor  1 40,067.76  9 ,000.00  1 49,067.76  12,779.01  208.12  no"
# "Bennett, Tim  Councilor  42,677.50  -  42,677.50  4,528.88  133.33  no"
PRINCE_GEORGE_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\ ]+?)"
    r"\ +(Mayor|Councilors?)\s+"
    r"(" + _NUM + r")"      # remuneration
    r"\s+(" + _NUM + r"|-)" # benefits or dash (skip — but capture to advance)
    r"\s+(?:" + _NUM + r")" # total (skip)
    r"\s+(" + _NUM + r"|-)", # expenses
    re.MULTILINE | re.IGNORECASE,
)

# Prince Rupert: "Mayor POND, HERBERT  $ 93,812  $ 37,053  $ 130,865"
POSITION_FIRST_RE = re.compile(
    r"^(Mayor|Councillors?)\s+"
    r"([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)"
    r"\s{2,}"
    r"\$?\s*(\d[\d,\.\s]*\d)"
    r"(?:\s+\$?\s*(\d[\d,\.\s]*\d|\-))?",
    re.MULTILINE | re.IGNORECASE,
)

# Delta: "Mayor G. Harvie  182,919  1 8,706  201,625  3,199  7,344"
#        "Councillor R. Binder  77,838  1 2,351  90,189  10,342  6,501"
DELTA_RE = re.compile(
    r"^(Mayor|Councillor)\s+"
    r"(?:[A-Z][\w\u00C0-\u024F\.\s]+?)"
    r"\s{2,}"
    r"\$?\s*(\d[\d,\.\s]*\d)"   # base remuneration
    r"(?:\s+\$?\s*[\d,\.\s]+)?" # car allowance (skip)
    r"(?:\s+\$?\s*[\d,\.\s]+)?" # total (skip)
    r"\s+\$?\s*(\d[\d,\.\s]*\d|\-)",  # expenses
    re.MULTILINE,
)

# Oak Bay: no position label — identify by highest remuneration
_EMPLOYEE_KEYWORDS = re.compile(
    r"\b(Fire|Manager|Assistant|General|Public|Corporate|Chief|Director|Engineer|"
    r"Planner|Clerk|Officer|Superintendent|Coordinator|Inspector|Analyst|"
    r"Commissioner|Administrator|Treasurer|Librarian|Solicitor|Controller)\b",
    re.IGNORECASE,
)

OAK_BAY_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)"
    r"\s+"
    r"\$?\s*(\d[\d,\.]*\d)"
    r"(?:\s+\$?\s*(\d[\d,\.]*\d|-))?",
    re.MULTILINE,
)

# Pitt Meadows: NAME  POSITION  Salary  Benefits/Other  Expenses
PITT_MEADOWS_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]*?)\s+"
    r"(MAYOR|COUNCILLOR)\s+"
    r"(\d[\d,]+)"
    r"\s+(\d[\d,]+)"
    r"\s+(\d[\d,]+)",
    re.MULTILINE | re.IGNORECASE,
)

# North Cowichan: Name  Position  Remuneration  Benefits  Expenses
NORTH_COWICHAN_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)"
    r"\s+(Mayor|Councillors?)\s+"
    r"\$?\s*(\d[\d,\.]+)"     # remuneration
    r"\s+\$?\s*(\d[\d,\.]+)"  # benefits
    r"\s+\$?\s*(\d[\d,\.]+|-)",  # expenses
    re.MULTILINE | re.IGNORECASE,
)

# Coquitlam: Name  Position  Remuneration  Taxable Benefits  Expenses
COQUITLAM_RE = re.compile(
    r"^([\w\u00C0-\u024F',\.\-\(\)][\w\u00C0-\u024F',\.\-\(\)\ ]+?)"
    r"\ +"
    r"(City Mayor|City Councillor|Mayor|Deputy Mayor|Councillors?|Council\b)"
    r"\ +"
    r"(" + _NUM + r")"      # remuneration
    r"\ +(" + _NUM + r"|-)" # taxable benefits
    r"\ +(" + _NUM + r"|-)", # expenses
    re.MULTILINE | re.IGNORECASE,
)


def _is_elected_section(text: str) -> bool:
    # Broad match: any page with remuneration-related keywords + dollar figures
    has_numbers = bool(re.search(r"\d{2,3},\d{3}", text))
    has_keyword = bool(re.search(
        r"elected\s+official|council\s+remuneration|remuneration.*council|"
        r"schedule.*remuneration|mayor.*councillor|councillor.*mayor|"
        r"\bMayor\b|\bCouncil(lor|or|)\b",
        text, re.IGNORECASE
    ))
    return has_numbers and has_keyword


def parse_standard(text: str) -> list[dict]:
    # Strip leading employee numbers (e.g. "12922 BARKMAN LESTER ...")
    text = re.sub(r"^\d{4,6}\s+", "", text, flags=re.MULTILINE)
    # Collapse OCR spaces inside numbers: "1 54,608" -> "154,608", "6 0,600" -> "60,600"
    # Collapse OCR spaces: only when a single digit follows whitespace and precedes a number
    # e.g. "Mayor 1 54,608" -> "Mayor 154,608" but NOT "27,712 10,201"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    rows = []
    for m in STANDARD_RE.finditer(text):
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp_raw = clean_amount(m.group(4)) if m.group(4) else 0
        exp = exp_raw if (exp_raw is not None and exp_raw < 500_000) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    return rows


def parse_position_first(text: str) -> list[dict]:
    rows = []
    for m in POSITION_FIRST_RE.finditer(text):
        pos = normalise_position(m.group(1))
        if not pos:
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) if m.group(4) else 0
        if rem and rem > 5_000:
            rows.append({"name": m.group(2).strip(), "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    return rows


def parse_delta(text: str) -> list[dict]:
    """Position Name  Remuneration  Car Allowance  Total  Expenses  Benefits
    Takes col 1 (remuneration) and col 4 (expenses). Heavy OCR spaces throughout."""
    # Collapse OCR spaces in large numbers: "7 7,838" -> "77,838", "3 ,199" -> "3,199"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    # Collapse OCR spaces in small numbers: "7 35" -> "735", "5 20" -> "520"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{2,3})(?=\s)", r"\1\2", text)
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"^(Mayor|Councillors?)\s+"
            r"([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s\.]+?)\s+"
            r"(\d[\d,]+)"       # remuneration (col 1)
            r"\s+(\d[\d,]+)"    # car allowance (col 2, skip)
            r"\s+(\d[\d,]+)"    # total (col 3, skip)
            r"\s+(\d[\d,]+|-)"  # expenses (col 4)
            r"\s+(\d[\d,]+|-)", # benefits (col 5)
            line.strip(), re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(1))
        if not pos:
            continue
        name = m.group(2).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(6)) or 0
        ben = clean_amount(m.group(7)) if m.group(7) and m.group(7).strip() != "-" else None
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows


def parse_oak_bay(text: str) -> list[dict]:
    """No position labels — return all rows; mayor identified as highest paid."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        m = OAK_BAY_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        # Skip totals / header lines
        if re.match(r"^\$|^total|^name|^schedule", name, re.IGNORECASE):
            continue
        # Skip sentence fragments and employee rows
        if not is_valid_name(name):
            continue
        if _EMPLOYEE_KEYWORDS.search(name):
            continue
        rem = clean_amount(m.group(2))
        exp = clean_amount(m.group(3)) if m.group(3) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_pitt_meadows(text: str) -> list[dict]:
    """NAME  POSITION  Salary  Other  Expenses — ALL CAPS, stop at TOTAL ELECTED OFFICIALS."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^TOTAL\s+ELECTED", line, re.IGNORECASE):
            break
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(MAYOR|COUNCILLOR)\s+"
            r"(\d[\d,]+)"       # salary (remuneration)
            r"\s+(\d[\d,]+)"    # benefits/other
            r"\s+(\d[\d,]+)",   # expenses
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4))
        exp = clean_amount(m.group(5)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows


def parse_north_cowichan(text: str) -> list[dict]:
    """Name  Position  $ rem  $ benefits  $ expenses — line by line."""
    rows = []
    for line in text.splitlines():
        m = NORTH_COWICHAN_RE.match(line.strip())
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4)) if m.group(4) else None
        exp = clean_amount(m.group(5)) if m.group(5) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": ben})
    return rows


def parse_prince_george(text: str) -> list[dict]:
    """Name  Position  Non-Expense Portion  Vehicle Allowance  Total  Expenses  Benefits
    Remuneration = col 1 + col 2, Expenses = col 4."""
    # Collapse OCR spaces inside numbers: "1 40,067.76" -> "140,067.76", "9 ,000.00" -> "9,000.00"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    rows = []
    for m in PRINCE_GEORGE_RE.finditer(text):
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        # col 2 is vehicle allowance — add to remuneration if present
        allowance = clean_amount(m.group(4)) if m.group(4) and m.group(4).strip() != "-" else 0
        exp = clean_amount(m.group(5)) if m.group(5) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": (rem or 0) + (allowance or 0),
                         "expenses": exp or 0,
                         "benefits": None})
    return rows


def parse_kamloops(text: str) -> list[dict]:
    """Name  Position  Remuneration  Taxable benefits  Total  [Council Rep]  Expenses
    Benefits extraction skipped — PDF layout produces incorrect values."""
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-\(\)][\w\u00C0-\u024F',\.\-\(\)\s]+?)\s+"
            r"(Mayor|Council)\s+"
            r"\$?\s*(\d[\d,]+)"          # remuneration
            r"(?:\s+\$?\s*[\d,]+)?"      # taxable benefits (skip)
            r"(?:\s+\$?\s*[\d,]+)?"      # total (skip)
            r"(?:\s+\$?\s*[\d,]+)?"      # council rep (skip)
            r"\s+\$?\s*(\d[\d,]*)",      # expenses
            line.strip(), re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) if m.group(4) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    return rows


def parse_coquitlam(text: str) -> list[dict]:
    """Name  Position  Remuneration  Taxable Benefits  Expenses — single regex, no tail parsing."""
    # Collapse OCR spaces inside numbers: "8 4,072" -> "84,072"
    text = re.sub(r"(?<!\d)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    rows = []
    for m in COQUITLAM_RE.finditer(text):
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4)) if m.group(4) and m.group(4).strip() != "-" else None
        exp = clean_amount(m.group(5)) if m.group(5) and m.group(5).strip() != "-" else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": ben})
    return rows


def parse_abbotsford(text: str) -> list[dict]:
    """Emp# Name  City Mayor/Councillor  Indemnity  Expenses  Total — take cols 1 & 2."""
    text = re.sub(r"^\d{4,6}\s+", "", text, flags=re.MULTILINE)
    # Collapse OCR space: leading 1-2 digit prefix before a number e.g. "1 54,608" -> "154,608"
    # Only collapse when preceded by a space (not mid-number)
    text = re.sub(r"(?<!\d)(\d{1,2})\s+(\d{2,3},\d{3})", r"\1\2", text)
    rows = []
    for match in STANDARD_RE.finditer(text):
        pos = normalise_position(match.group(2))
        if not pos:
            continue
        name = match.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(match.group(3))
        exp = clean_amount(match.group(4)) if match.group(4) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    return rows


# ...existing code...


def parse_quesnel(text: str) -> list[dict]:
    """Section headers 'Mayor' / 'Councillors' on their own lines, then
    FirstName LastName  $ rem  exp on subsequent lines."""
    current_pos = None
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^Mayor\s*$", line, re.IGNORECASE):
            current_pos = "Mayor"
            continue
        if re.match(r"^Councillors?\s*$", line, re.IGNORECASE):
            current_pos = "Councillor"
            continue
        if current_pos is None:
            continue
        if re.match(r"^(Total|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F\-]+\s+[\w\u00C0-\u024F\-]+)\s+"  # Surname FirstName
            r"\$?\s*(\d[\d,]+)"         # remuneration
            r"\s+\$?\s*(\d[\d,]+|-)",   # expenses
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        exp = clean_amount(m.group(3)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": current_pos,
                         "remuneration": rem, "expenses": exp})
        # After Mayor row, next section is Councillors
        if current_pos == "Mayor":
            current_pos = None
    return rows


def parse_port_alberni(text: str) -> list[dict]:
    """Name  Elected Official  $ rem  $ taxable benefits  $ expenses
    OCR spaces in amounts. Highest paid = Mayor. Benefits extraction skipped."""
    # Collapse OCR spaces: "3 0,010.33" -> "30,010.33", "9 4.71" -> "94.71"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,2}\.\d{2})(?=\s|$)", r"\1\2", text)
    # Fix "3 .98" -> "3.98" (digit + space + decimal point)
    text = re.sub(r"(\d)\s+\.(\d+)", r"\1.\2", text)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Total|Name|Taxable|Schedule|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"Elected\s+Official\s+"
            r"\$\s*(\d[\d,\.]+)"        # remuneration
            r"\s+\$\s*(\d[\d,\.]+|-)"   # taxable benefits (skip)
            r"\s+\$\s*(\d[\d,\.]+|-)",  # expenses
            line, re.IGNORECASE
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        exp = clean_amount(m.group(4)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_new_westminster(text: str) -> list[dict]:
    """No position labels. Remuneration = col 1; expenses = sum of remaining cols.
    Highest paid = Mayor."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Total|Council|Schedule|City|UBCM|LMLGA|The |$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(\d[\d,]+)"                           # remuneration
            r"((?:\s+(?:\d[\d,]+|-))+)",            # remaining expense columns
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        # Sum all expense sub-columns
        exp_tokens = re.findall(r"\d[\d,]*", m.group(3))
        exp = sum(clean_amount(t) or 0 for t in exp_tokens)
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_chilliwack(text: str) -> list[dict]:
    """Position Name  Bylaw Rate  Other  Mileage  Expenses
    Remuneration = col 1 + col 2, expenses = col 4."""
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"^(Mayor|Councillors?)\s+"
            r"([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"\$?\s*(\d[\d,\.]+)"       # bylaw rate
            r"\s+\$?\s*(\d[\d,\.]+|-)"  # other
            r"\s+\$?\s*(\d[\d,\.]+|-)"  # mileage (skip)
            r"\s+\$?\s*(\d[\d,\.]+|-)", # expenses
            line.strip(), re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(1))
        if not pos:
            continue
        name = m.group(2).strip()
        if not is_valid_name(name):
            continue
        bylaw = clean_amount(m.group(3)) or 0
        other = clean_amount(m.group(4)) or 0
        exp   = clean_amount(m.group(6)) or 0
        rem = bylaw + other
        if rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    return rows


def parse_burnaby(text: str) -> list[dict]:
    """Name  Remuneration  Allowances and Benefits  Expenses -- no position labels.
    Takes col 1 (remuneration), col 2 (benefits), col 3 (expenses); highest paid = Mayor."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Name|Total|Note|Schedule|\(|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(\d[\d,]+)"       # remuneration
            r"\s+(\d[\d,]+)"    # allowances (skip)
            r"\s+(\d[\d,]+)",   # expenses
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        ben = clean_amount(m.group(3))
        exp = clean_amount(m.group(4))
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": ben})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_victoria(text: str) -> list[dict]:
    """COUNCIL MEMBER  Remuneration  Taxable Benefits  Expenses — no position labels.
    Collapses OCR spaces; takes col 1 (remuneration) and col 3 (expenses).
    Highest paid = Mayor."""
    # Collapse OCR spaces: "2 ,586" -> "2,586", "8 ,412" -> "8,412", "1 65" -> "165"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    text = re.sub(r"(?<=\s)(\d)\s+(\d{2,3})(?=\s|$)", r"\1\2", text)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(TOTAL|COUNCIL MEMBER|TAXABLE|THE |STATEMENT|CITY OF|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"\$?\s*(\d[\d,]+)"         # remuneration
            r"\s+\$?\s*(\d[\d,]+|-)"    # taxable benefits (skip)
            r"\s+(\d[\d,]+|-)",         # expenses
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        exp = clean_amount(m.group(4)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_esquimalt(text: str) -> list[dict]:
    """FirstName LastName  Remuneration  Expenses — no position labels, no commas in names.
    Highest paid = Mayor."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Name|Total|Schedule|The |$|\d)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F\s\-]+?)\s+"
            r"(\d[\d,\.]+)"         # remuneration
            r"\s+(\d[\d,\.]+)",     # expenses
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        exp = clean_amount(m.group(3)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_prince_rupert(text: str) -> list[dict]:
    """Mayor NAME  rem  exp  /  Councillors (header) then NAME  rem  exp per line.
    Collapses OCR spaces in amounts."""
    # Collapse OCR spaces: "3 7,053" -> "37,053", "6 ,043" -> "6,043"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    rows = []
    current_pos = None
    for line in text.splitlines():
        line = line.strip()
        # Mayor line: "Mayor POND, HERBERT $ 93,812 $ 37,053 $ 130,865"
        m_mayor = re.match(
            r"^Mayor\s+"
            r"([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"\$?\s*(\d[\d,]+)"      # remuneration
            r"\s+\$?\s*(\d[\d,]+)",  # expenses
            line, re.IGNORECASE
        )
        if m_mayor:
            current_pos = "Councillor"  # subsequent lines are councillors
            name = m_mayor.group(1).strip()
            rem = clean_amount(m_mayor.group(2))
            exp = clean_amount(m_mayor.group(3)) or 0
            if rem and rem > 5_000:
                rows.append({"name": name, "position": "Mayor",
                             "remuneration": rem, "expenses": exp,
                             "benefits": None})
            continue
        # "Councillors NAME ..." — strip the header word and parse as councillor
        line = re.sub(r"^Councillors?\s+", "", line, flags=re.IGNORECASE)
        # Councillor data line: "ADEY, NICHOLAS 23,453 6,043 29,496"
        if current_pos == "Councillor":
            m_coun = re.match(
                r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
                r"(\d[\d,]+)"       # remuneration
                r"\s+(\d[\d,]+)"    # expenses
                r"(?:\s+\d[\d,]+)?",  # total (optional, skip)
                line
            )
            if m_coun:
                name = m_coun.group(1).strip()
                if not is_valid_name(name):
                    continue
                rem = clean_amount(m_coun.group(2))
                exp = clean_amount(m_coun.group(3)) or 0
                if rem and rem > 5_000:
                    rows.append({"name": name, "position": "Councillor",
                                 "remuneration": rem, "expenses": exp,
                                 "benefits": None})
    return rows


def parse_comox(text: str) -> list[dict]:
    # ...existing code...
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?),\s*"
            r"(Mayor|Deputy Mayor|Councillors?|Councilors?)\s+"
            r"\$?\s*(\d[\d,\.]+)"
            r"(?:\s+\$?\s*(\d[\d,\.]+|-))?",
            line.strip(), re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) if m.group(4) else 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp or 0,
                         "benefits": None})
    return rows


def parse_maple_ridge(text: str) -> list[dict]:
    """Name  Position  Remuneration  Taxable Benefits & Other  Expenses"""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Name|Total|Remuneration|Benefits|Schedule|City|Financial|Statement|Elected|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(Mayor|Councillors?|Deputy Mayor)\s+"
            r"(\d[\d,\.]+)"         # remuneration
            r"\s+(\d[\d,\.]+|-)"    # taxable benefits & other
            r"\s+(\d[\d,\.]+|-)",   # expenses
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4)) if m.group(4) and m.group(4).strip() != "-" else None
        exp = clean_amount(m.group(5)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows


def parse_port_coquitlam(text: str) -> list[dict]:
    """Name  Position  Base  Benefits & Other Compensation  Expenses  Total"""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Name|Total|Benefits|Expenses|The |Schedule|Prepared|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(Mayor|Councillors?|Deputy Mayor)\s+"
            r"(\d[\d,]+)"           # base (remuneration)
            r"\s+(\d[\d,]+|-)"      # benefits & other compensation
            r"\s+(\d[\d,]+|-)"      # expenses
            r"(?:\s+\$?\s*[\d,]+)?",# total (skip)
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4)) if m.group(4) and m.group(4).strip() != "-" else None
        exp = clean_amount(m.group(5)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows


def parse_salmon_arm(text: str) -> list[dict]:
    """Name  Position  Remuneration  Expenses  Benefit  Total
    Benefits is the third numeric column (after expenses)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(Name|Total|Statement|Life|For the|A statement|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(Mayor|Councillors?)\s+"
            r"\$?\s*(\d[\d,]+)"         # remuneration
            r"\s+\$?\s*(\d[\d,]+|-)"    # expenses
            r"\s+\$?\s*(\d[\d,]+|-)"    # benefit
            r"(?:\s+\$?\s*[\d,]+)?",    # total (skip)
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) or 0
        ben = clean_amount(m.group(5)) if m.group(5) and m.group(5).strip() != "-" else None
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows


def parse_sidney(text: str) -> list[dict]:
    """NAME  POSITION  GROSS  BENEFITS  TOTAL  EXPENSES — heavy OCR spaces in amounts."""
    # Collapse OCR spaces in numbers with commas: "4 5,122" -> "45,122", "8 ,060" -> "8,060"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{1,3},\d{3})", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    # Collapse OCR spaces in small numbers without commas: "8 98" -> "898", "5 51" -> "551"
    text = re.sub(r"(?<=\s)(\d)\s+(\d{2,3})(?=\s|$)", r"\1\2", text)
    # ...existing code...
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(NAME|TOTAL|STATEMENT|SCHEDULE|YEAR|ELECTED|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(Mayor|Councillors?)\s+"
            r"\$?\s*(\d[\d,]+)"         # gross (remuneration)
            r"\s+\$?\s*(\d[\d,]+|-)"    # benefits
            r"\s+\$?\s*(\d[\d,]+|-)"    # total (skip)
            r"\s+\$?\s*(\d[\d,]+|-)",   # expenses
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        ben = clean_amount(m.group(4)) if m.group(4) and m.group(4).strip() != "-" else None
        exp = clean_amount(m.group(6)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    return rows



def parse_saanich(text: str) -> list[dict]:
    """ELECTED OFFICIAL  POSITION  REMUNERATION  EXPENSES — clean layout, no benefits."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(ELECTED|Name|Total|\$|Schedule|Corporation|Statement|For the|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"(Mayor|Councillors?)\s+"
            r"\$?\s*(\d[\d,]+)"         # remuneration
            r"\s+\$?\s*(\d[\d,]+|-)",   # expenses
            line, re.IGNORECASE
        )
        if not m:
            continue
        pos = normalise_position(m.group(2))
        if not pos:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    return rows


def parse_kelowna(text: str) -> list[dict]:
    """Surname  First Initial  Remuneration ($)  Expenses ($)
    Section headers 'Mayor' / 'Councillors' on their own lines.
    OCR spaces in amounts handled by clean_amount."""
    current_pos = None
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^Mayor\s*$", line, re.IGNORECASE):
            current_pos = "Mayor"
            continue
        if re.match(r"^Councillors?\s*$", line, re.IGNORECASE):
            current_pos = "Councillor"
            continue
        if current_pos is None:
            continue
        if re.match(r"^(Total|Surname|Taxable|City of|Council|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-]+(?:\s+[\w\u00C0-\u024F',\.\-]+)?)\s+"
            r"([A-Z])\s+"               # first initial
            r"\$?\s*(\d[\d,\s]+)"       # remuneration (may have OCR spaces)
            r"\s+\$?\s*([\d,\s]+|-)",   # expenses (may have OCR spaces)
            line
        )
        if not m:
            continue
        surname = m.group(1).strip()
        initial = m.group(2).strip()
        name = f"{surname} {initial}"
        if not is_valid_name(surname):
            continue
        rem = clean_amount(m.group(3))
        exp = clean_amount(m.group(4)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": current_pos,
                         "remuneration": rem, "expenses": exp,
                         "benefits": None})
    return rows


def parse_surrey(text: str) -> list[dict]:
    """Name  Base Salary  Separation Allowance  Taxable Benefits  Expenses  Total
    OCR spaces in amounts. Highest paid = Mayor. Benefits extracted.
    Mayor row has $ signs; councillor rows do not."""
    # Collapse OCR spaces only within a single number token:
    # "1 70,975" -> "170,975"  but NOT across column boundaries
    # Only collapse digit+space+digit when followed by exactly one comma-group
    text = re.sub(r"(?<!\d)(\d)\s+(\d{2},\d{3}|\d{3},\d{3})(?!\d)", r"\1\2", text)
    text = re.sub(r"(\d)\s+,(\d{3})", r"\1,\2", text)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^(ELECTED|BASE|Name|Total|\$|Per Statement|Variance|Taxable|Page|Elected Officials|$)", line, re.IGNORECASE):
            continue
        m = re.match(
            r"^([\w\u00C0-\u024F',\.\-][\w\u00C0-\u024F',\.\-\s]+?)\s+"
            r"\$?\s*(\d[\d,]+)"         # base salary (remuneration)
            r"\s+\$?\s*(\d[\d,]+)"      # separation allowance (skip)
            r"\s+\$?\s*(\d[\d,]+)"      # taxable benefits
            r"\s+\$?\s*(\d[\d,]+)"      # expenses
            r"(?:\s+\$?\s*[\d,]+)?",    # total (skip)
            line
        )
        if not m:
            continue
        name = m.group(1).strip()
        if not is_valid_name(name):
            continue
        rem = clean_amount(m.group(2))
        ben = clean_amount(m.group(4))
        exp = clean_amount(m.group(5)) or 0
        if rem and rem > 5_000:
            rows.append({"name": name, "position": None,
                         "remuneration": rem, "expenses": exp,
                         "benefits": ben})
    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


def parse_vancouver(text: str) -> list[dict]:
    """Fallback text parser — not used when page object is available."""
    return []


def parse_vancouver_page(page) -> list[dict]:
    """Bbox word-group parser for Vancouver — handles extreme character-level OCR spacing.
    Columns: Name  Remuneration  Local Expenses  Travel & Conferences  Discretionary Expenses
    Expenses = sum of cols 2+3+4. Highest paid = Mayor."""
    from collections import defaultdict

    words = page.extract_words(x_tolerance=3, y_tolerance=3)

    # Group words into rows by top coordinate (bucket to nearest 2px)
    rows_by_top = defaultdict(list)
    for w in words:
        row_key = round(w["top"] / 2) * 2
        rows_by_top[row_key].append(w)

    # Data rows: top between ~130 and ~280 (header rows are ~90-120, totals/notes ~285+)
    # Identify column x-positions from header row (top ~116): Name(1), (2), (3), (4)
    # Name is leftmost (~x0=90), then 4 numeric columns spread across page
    # From session output: rem at ~x0=240, local_exp ~x0=320, travel ~x0=400, discret ~x0=480

    rows = []
    for top in sorted(rows_by_top):
        row_words = sorted(rows_by_top[top], key=lambda w: w["x0"])

        # Skip header/footer rows
        joined = " ".join(w["text"] for w in row_words)
        if re.search(r"(MAYOR|REMUNERATION|Name|Travel|Local|Discret|\(1\)|\(2\)|\(3\)|\(4\)|Total|^\$)", joined, re.IGNORECASE):
            continue
        if top > 285:  # totals/notes section
            break

        # Collapse character-spaced tokens into clean strings grouped by x position
        # Words with x0 < 220 are the name; others are numeric columns
        name_words = [w["text"] for w in row_words if w["x0"] < 220]
        num_words  = [w for w in row_words if w["x0"] >= 220]

        if not name_words or not num_words:
            continue

        # Collapse name tokens — strip single-char OCR fragments into full tokens
        # e.g. ["S", "im", ",", "K"] -> "Sim, K"
        raw_name = "".join(name_words)
        # Clean up: ensure comma-space between surname and initial
        raw_name = re.sub(r",([A-Z])", r", \1", raw_name)

        # Collapse numeric tokens — join and then parse out 4 numbers
        num_str = " ".join(w["text"] for w in num_words)
        # Remove $ signs and collapse OCR digit spacing
        num_str = re.sub(r"\$", "", num_str)
        num_str = re.sub(r"(\d)\s+(\d)", r"\1\2", num_str)
        num_str = re.sub(r"(\d)\s+,(\d)", r"\1,\2", num_str)

        # Extract up to 4 numbers
        nums = re.findall(r"\d[\d,]*", num_str)
        if len(nums) < 1:
            continue

        # Clean each amount
        amounts = [clean_amount(n) for n in nums[:4]]
        rem = amounts[0] if amounts else None
        exp_parts = amounts[1:]  # local, travel, discretionary
        exp = sum(v for v in exp_parts if v is not None and v != 0) if exp_parts else 0

        if not rem or rem < 5_000:
            continue
        if not is_valid_name(raw_name):
            continue

        rows.append({
            "name":         raw_name,
            "position":     None,
            "remuneration": rem,
            "expenses":     exp,
            "benefits":     None,
        })

    if not rows:
        return rows
    max_rem = max(r["remuneration"] for r in rows)
    for r in rows:
        r["position"] = "Mayor" if r["remuneration"] == max_rem else "Councillor"
    return rows


# ---------------------------------------------------------------------------
# Per-municipality dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    "Abbotsford":      parse_abbotsford,
    "Burnaby":         parse_burnaby,
    "Chilliwack":      parse_chilliwack,
    "Comox":           parse_comox,
    "Coquitlam":       parse_coquitlam,
    "Delta":           parse_delta,
    "Esquimalt":       parse_esquimalt,
    "Kamloops":        parse_kamloops,
    "Kelowna":         parse_kelowna,
    "Maple Ridge":     parse_maple_ridge,
    "New Westminster": parse_new_westminster,
    "North Cowichan":  parse_north_cowichan,
    "Oak Bay":         parse_oak_bay,
    "Pitt Meadows":    parse_pitt_meadows,
    "Port Alberni":    parse_port_alberni,
    "Port Coquitlam":  parse_port_coquitlam,
    "Prince George":   parse_prince_george,
    "Prince Rupert":   parse_prince_rupert,
    "Quesnel":         parse_quesnel,
    "Saanich":         parse_saanich,
    "Salmon Arm":      parse_salmon_arm,
    "Sidney":          parse_sidney,
    "Surrey":          parse_surrey,
    "Vancouver":       parse_vancouver,
    "Victoria":        parse_victoria,
}


def extract_from_pdf(pdf_path: Path, municipality: str) -> list[dict]:
    parser = PARSERS.get(municipality, parse_standard)
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() or ""
    return parser(text)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _municipality_from_watermark(text: str) -> str | None:
    """Extract municipality name from watermark line e.g. 'Abbotsford — 2024'.
    Also handles Vancouver's non-standard multi-line header."""
    # Vancouver header spans multiple lines — check full page text
    if re.search(r"MAYOR AND COUNCILLORS.*CITY OF VANCOUVER", text, re.IGNORECASE | re.DOTALL):
        return "Vancouver"
    # Standard watermark: first non-empty line is "Municipality — 2024"
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    m = re.match(r"^(.+?)\s*[—\-–]\s*\d{4}", first_line)
    if m:
        return m.group(1).strip()
    return None


def extract_all(merged_pdf: str = "app/remuneration_schedules_2024.pdf") -> pd.DataFrame:
    merged_path = Path(merged_pdf)
    if not merged_path.exists():
        raise FileNotFoundError(f"Merged PDF not found: {merged_path}")

    records = []

    with pdfplumber.open(merged_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            municipality = _municipality_from_watermark(text)
            if not municipality:
                first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
                print(f"WARN: could not identify municipality from watermark: {first_line!r}")
                continue

            print(f"Reading {municipality} ...", end=" ", flush=True)
            try:
                # Vancouver needs bbox page object due to extreme character OCR spacing
                if municipality == "Vancouver":
                    rows = parse_vancouver_page(page)
                else:
                    parser = PARSERS.get(municipality, parse_standard)
                    body = "\n".join(text.splitlines()[1:])
                    rows = parser(body)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            if not rows:
                print("WARN: no rows found")
                continue

            print(f"{len(rows)} rows")
            for row in rows:
                records.append({
                    "municipality": municipality,
                    "year":         YEAR,
                    "name":         row["name"],
                    "position":     row["position"],
                    "remuneration": row["remuneration"],
                    "expenses":     row["expenses"],
                    "benefits":     row.get("benefits"),
                })

    if not records:
        return pd.DataFrame(columns=["municipality", "year", "name", "position", "remuneration", "expenses", "benefits"])

    df = pd.DataFrame(records).astype({
        "municipality": "string",
        "year":         "int32",
        "name":         "string",
        "position":     "string",
        "remuneration": "int32",
        "expenses":     "int32",
    })
    return df


if __name__ == "__main__":
    df = extract_all()

    # Merge manual remuneration for image-based PDFs
    manual_path = Path("data_prep/manual_remuneration_2024.csv")
    if manual_path.exists():
        manual = pd.read_csv(manual_path).dropna(subset=["remuneration"])
        if not manual.empty:
            if "benefits" not in manual.columns:
                manual["benefits"] = None
            else:
                # Convert to nullable Int32 so NaN stays NaN (not float)
                manual["benefits"] = pd.array(manual["benefits"], dtype="Int32")
            manual = manual.astype({
                "municipality": "string",
                "year": "int32",
                "name": "string",
                "position": "string",
                "remuneration": "int32",
                "expenses": "int32",
            })
            df = pd.concat([df, manual], ignore_index=True)

    # Sort so Mayor appears first within each municipality
    df["_pos_order"] = df["position"].map({"Mayor": 0, "Councillor": 1}).fillna(2).astype(int)
    df = df.sort_values(["municipality", "_pos_order"]).drop(columns="_pos_order").reset_index(drop=True)
    # ...existing code...
    import json

    output = []
    for muni, group in df.groupby("municipality", sort=True):
        output.append({
            "year":        int(group["year"].iloc[0]),
            "municipality": str(muni),
            "councillors": [
                {
                    "name":         row["name"],
                    "position":     row["position"],
                    "remuneration": int(row["remuneration"]),
                    "expenses":     int(row["expenses"]),
                    "benefits":     int(row["benefits"]) if pd.notna(row.get("benefits")) and row.get("benefits") is not None else None,
                }
                for _, row in group.iterrows()
            ]
        })

    out = Path("data_prep/remuneration_2024.json")
    with open(out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {len(df)} rows → {out}")
    print(df.to_string())
