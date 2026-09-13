"""Build the accompanying note as a PDF from docs/report/nota.md.

Markdown -> HTML (python-markdown) -> Chrome headless --print-to-pdf. Figures are
referenced with relative paths from the markdown and embedded as data URIs so the
HTML is self-contained.

Usage (from repo root):  cv-service\\.venv\\Scripts\\python.exe docs\\report\\build.py
"""

from __future__ import annotations

import base64
import mimetypes
import re
import shutil
import subprocess
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "nota.md"
HTML = HERE / "nota.html"
PDF = HERE / "immobiliare-photo-lab-nota.pdf"

CSS = """
@page { size: A4; margin: 11mm 12mm 11mm 12mm; }
html { font-size: 8.6pt; }
body { font-family: "Segoe UI", "Inter", system-ui, sans-serif; color: #241f1b; line-height: 1.3; max-width: 100%; }
h1 { font-family: Georgia, "Fraunces", serif; font-weight: 600; font-size: 17pt; margin: 0 0 2pt; }
h1 + p em { color: #7d7265; }
h2 { font-family: Georgia, serif; font-weight: 600; font-size: 11.5pt; margin: 9pt 0 3pt; page-break-after: avoid; color: #241f1b; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; page-break-after: avoid; }
p { margin: 0 0 5pt; text-align: justify; hyphens: auto; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.4pt; page-break-inside: avoid; }
th, td { border-bottom: 1px solid #e8e0d4; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { font-weight: 600; color: #514840; background: #f6f1e9; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt; background: #f3eee6; padding: 0 3pt; border-radius: 3px; }
pre { background: #f3eee6; padding: 8pt 10pt; border-radius: 6px; font-size: 8.8pt; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
figure { margin: 5pt 0 7pt; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; max-height: 118mm; border: 1px solid #e8e0d4; border-radius: 6px; }
figure.wide img { max-height: 32mm; }
figcaption { font-size: 7.8pt; color: #7d7265; margin-top: 4pt; text-align: center; }
hr { border: 0; border-top: 1px solid #d6cbbb; margin: 18pt 0; page-break-after: always; }
a { color: #a94430; text-decoration: none; }
ul, ol { margin: 0 0 5pt; padding-left: 16pt; }
li { margin-bottom: 2pt; }
"""


def embed(src: str) -> str:
    path = (HERE / src).resolve()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    # ![caption](path) -> <figure> with the image embedded; wide canvases get a smaller cap
    def fig(m: re.Match) -> str:
        caption, src = m.group(1), m.group(2)
        cls = ' class="wide"' if "screenshots" in src else ""
        return f'<figure{cls}><img src="{embed(src)}" alt=""><figcaption>{caption}</figcaption></figure>'
    text = re.sub(r"!\[(.*?)\]\((.*?)\)", fig, text)
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    HTML.write_text(f"<!doctype html><html lang='it'><head><meta charset='utf-8'><title>immobiliare-photo-lab — nota</title>"
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    chrome = next((c for c in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome") or "", shutil.which("google-chrome") or "",
    ] if c and Path(c).exists()), None)
    if not chrome:
        raise SystemExit("Chrome not found; open nota.html and print to PDF")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={PDF}", HTML.as_uri()], check=True, capture_output=True)
    print(f"-> {PDF.relative_to(ROOT)} ({PDF.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
