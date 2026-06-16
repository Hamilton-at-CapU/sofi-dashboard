import io
import re
import pdfplumber
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import Color

YEAR = 2023

IMAGE_MUNIS = {
    "Campbell River",   # image-based PDF, no extractable text
    "Comox",            # image-based PDF, no extractable text
    "Esquimalt",        # image-based PDF, no extractable text
    "Mission",          # image-based PDF, no extractable text
    "Penticton",        # garbled/encoded text - effectively image-based
    "Pitt Meadows",     # image-based PDF, no extractable text
    "Richmond",         # image-based PDF (CNCL page numbers only)
    "Sechelt",          # image-based PDF, no extractable text
    "Squamish",         # image-based PDF, no extractable text
    "Terrace",          # image-based PDF, no extractable text
    "View Royal",       # CID-encoded pages, image-based
}

SLOW_MUNIS = {"Nelson", "Pitt Meadows"}

# 0-based page indices for municipalities whose remuneration pages
# cannot be reliably detected by text filters alone
PAGE_OVERRIDES = {
    "Burnaby":                  [39],   # p40 Mayor and Council remuneration (38=employee header, 59=employee)
    "Campbell River":           [4],    # p5
    "Coldstream":               [65],   # p66 Schedule of Remuneration and Expenses - Elected Officials
    "Comox":                    [32],   
    "Esquimalt":                [8],
    "Fort St. John":            [3],    # p4  "SCHEDULE OF RENUMERATION AND EXPENSES" (sic) - elected officials
    "Kamloops":                 [4],    # p5  elected officials (p7 = employees)
    "Maple Ridge":              [40],   # p41 elected officials (p4 = compliance text)
    "Mission":                  [5],
    "Nanaimo":                  [4],    # p5  Part E elected officials
    "New Westminster":          [40],   # p41 Schedule of Council Remuneration and Expenses
    "North Cowichan":           [5],    # p6  Schedule of Remuneration and Expenses
    "North Saanich":            [41],  
    "North Vancouver (City)":   [33],   # p34 elected officials (p38 = employees)
    "Penticton":                [2],
    "Pitt Meadows":             [29],   # p30 elected officials
    "Powell River":             [59],   # p60 elected officials remuneration
    "Richmond":                 [41],
    "Saanich":                  [40],
    "Sechelt":                  [2],
    "Sooke":                    [32],
    "Squamish":                 [39],
    "Surrey":                   [67],
    "Terrace":                  [1],
    "Vancouver":                [75],   # p76 Mayor and Councillors Remuneration and Expenses
    "Victoria":                 [49],   # p50 Statement of Council Remuneration and Expenses
    "View Royal":               [74],
    "West Kelowna":             [5],
    "West Vancouver":           [40],   # p41 Mayor and Councillors (p46 = employees)
    "Williams Lake":            [27],   # p28 page 1 of 2 - elected officials
}

# Primary: "schedule" + "remuneration" on the same line
TITLE_RE = re.compile(
    r"^.*\bschedule\b.*\bremuneration\b|^.*\bremuneration\b.*\bschedule\b",
    re.IGNORECASE | re.MULTILINE,
)

# Fallback: "council" or "elected" on the same line as "remuneration"
FALLBACK_RE = re.compile(
    r"^.*(council|elected\s+official).*remuneration|^.*remuneration.*(council|elected\s+official).*$",
    re.IGNORECASE | re.MULTILINE,
)

# Page must also mention an elected official keyword anywhere
ELECTED_RE = re.compile(
    r"\b(mayor|councillor|councilor|elected\s+official)\b",
    re.IGNORECASE,
)

# Exclude employee schedule pages
EMPLOYEE_RE = re.compile(
    r"employee\s+remuneration|employees\s+earning|excluding.*elected",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(r"\d{2,3},\d{3}")

# Dot/dash leaders (........ or --------) indicate a table of contents page
TOC_RE = re.compile(r"\.{4,}|\-{4,}")


def is_remuneration_page(text: str) -> bool:
    if len(TOC_RE.findall(text)) >= 5:
        return False
    if EMPLOYEE_RE.search(text):
        return False
    if not AMOUNT_RE.search(text):
        return False
    if not ELECTED_RE.search(text):
        return False
    return bool(TITLE_RE.search(text) or FALLBACK_RE.search(text))


def find_remuneration_page_numbers(pdf_path):
    indices = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if is_remuneration_page(text):
                indices.append(i)
    return indices


def make_watermark(municipality: str, year: int, page_width: float, page_height: float, rotation: int = 0) -> PdfReader:
    """Create an in-memory PDF page with a municipality/year label, accounting for rotation."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    label = f"{municipality} — {year}"
    banner_h = 22

    if rotation == 90:
        # Displayed top = left edge of mediabox; draw a vertical banner strip on the left
        c.setFillColor(Color(0.1, 0.1, 0.4, alpha=0.75))
        c.rect(0, 0, banner_h, page_height, fill=1, stroke=0)
        c.setFillColor(Color(1, 1, 1))
        c.setFont("Helvetica-Bold", 11)
        c.saveState()
        c.translate(15, 8)
        c.rotate(90)
        c.drawString(0, 0, label)
        c.restoreState()
    else:
        # Default (rotation == 0): banner at top of mediabox
        c.setFillColor(Color(0.1, 0.1, 0.4, alpha=0.75))
        c.rect(0, page_height - banner_h, page_width, banner_h, fill=1, stroke=0)
        c.setFillColor(Color(1, 1, 1))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(8, page_height - 15, label)

    c.save()
    buf.seek(0)
    return PdfReader(buf)


def stamp_watermark(page, municipality: str, year: int):
    """Stamp a watermark onto a page, accounting for page rotation."""
    w = float(page.mediabox.width)
    h = float(page.mediabox.height)
    rotation = page.get("/Rotate", 0) or 0
    watermark_reader = make_watermark(municipality, year, w, h, rotation)
    page.merge_page(watermark_reader.pages[0])
    return page


def build_merged_pdf(
    base_dir="data_prep/sofi_reports",
    output_path="data_prep/remuneration_pages_2023.pdf",
):
    base = Path(base_dir)
    writer = PdfWriter()
    total_pages = 0

    for muni_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        municipality = muni_dir.name
        year_dir = muni_dir / str(YEAR)

        if not year_dir.exists():
            print(f"SKIP  no {YEAR} folder:  {municipality}")
            continue
        pdfs = list(year_dir.glob("*.pdf")) or list(year_dir.glob("*.PDF"))
        if not pdfs:
            print(f"SKIP  no PDF:            {municipality}")
            continue

        pdf_path = pdfs[0]
        print(f"Scanning {municipality} ...", end=" ", flush=True)

        if municipality in PAGE_OVERRIDES:
            page_indices = PAGE_OVERRIDES[municipality]
            print(f"{len(page_indices)} page(s) at indices {page_indices} [override]")
        else:
            page_indices = find_remuneration_page_numbers(pdf_path)
            if not page_indices:
                print("WARN: no remuneration pages found")
                continue
            print(f"{len(page_indices)} page(s) at indices {page_indices}")

        reader = PdfReader(pdf_path)
        for idx in page_indices:
            page = reader.pages[idx]
            page = stamp_watermark(page, municipality, YEAR)
            writer.add_page(page)
            total_pages += 1

    out = Path(output_path)
    with open(out, "wb") as f:
        writer.write(f)

    print(f"\nWrote {total_pages} pages → {out}")


if __name__ == "__main__":
    build_merged_pdf()
