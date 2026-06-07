"""
Quickly classify all PDFs in sofi_reports as text-based or image-based.
Uses pypdf for speed (no layout parsing, just raw text stream).
"""

from pypdf import PdfReader
from pathlib import Path

base = Path("data_prep/sofi_reports")

text_pdfs = []
image_pdfs = []

for pdf_path in sorted(base.rglob("*.pdf")):
    print(f"Checking: {pdf_path}")
    reader = PdfReader(pdf_path)
    text = reader.pages[0].extract_text() or ""
    if len(text.strip()) > 50:
        kind = "text"
        text_pdfs.append(pdf_path)
    else:
        kind = "image"
        image_pdfs.append(pdf_path)
    print(f"  -> {kind}")

print(f"\nText-based:  {len(text_pdfs)}")
print(f"Image-based: {len(image_pdfs)}")

if image_pdfs:
    print("\nImage-based PDFs:")
    for p in image_pdfs:
        print(f"  {p}")
