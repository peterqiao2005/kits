import csv
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup


INDEX_URL = "https://artofproblemsolving.com/wiki/index.php/AMC_10_Problems_and_Solutions"
WIKI_BASE = "https://artofproblemsolving.com/wiki/index.php/"


@dataclass
class Entry:
    year: int
    series: str  # "10", "10A", or "10B"
    base_slug: str  # e.g. "2014_AMC_10B"
    problems_url: str
    pdf_url: Optional[str]
    status: str


def ensure_dirs(root: str) -> Dict[str, str]:
    out_dir = os.path.abspath(root)
    pdf_dir = os.path.join(out_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    return {"root": out_dir, "pdfs": pdf_dir}


def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
        return None
    except requests.RequestException:
        return None


def parse_index_for_bases(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    bases: List[str] = []

    # Match slugs like 2000_AMC_10, 2001_AMC_10, 2014_AMC_10A, 2014_AMC_10B, ... up to 2024
    pattern = re.compile(r"^(20\d{2})_AMC_10(A|B)?$")

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href.startswith("/wiki/index.php/"):
            continue
        slug = href.split("/wiki/index.php/")[-1]
        m = pattern.match(slug)
        if not m:
            continue
        year = int(m.group(1))
        if year < 2000 or year > 2024:
            continue
        bases.append(slug)

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    return uniq


def find_pdf_url_from_problems_page(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    # Strategy 1: any anchor with href ending with .pdf
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            # Normalize to absolute URL
            if href.startswith("/"):
                return f"https://artofproblemsolving.com{href}"
            elif href.startswith("http://") or href.startswith("https://"):
                return href
    # Strategy 2: anchor text contains 'PDF'
    for a in soup.select("a[href]"):
        text = (a.get_text(separator=" ") or "").strip().lower()
        if "pdf" in text:
            href = a["href"]
            if href.startswith("/"):
                return f"https://artofproblemsolving.com{href}"
            elif href.startswith("http://") or href.startswith("https://"):
                return href
            elif href.startswith("//"):
                return f"https:{href}"
    # Strategy 3: known AoPS community download pattern
    m = re.search(r'href="([^"]*?/community/contests/download/[^\"]+)"', html, re.IGNORECASE)
    if m:
        href = m.group(1)
        if href.startswith("/"):
            return f"https://artofproblemsolving.com{href}"
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return f"https://artofproblemsolving.com/{href}"
    return None


def collect_entries() -> List[Entry]:
    index_html = fetch(INDEX_URL)
    bases: List[str] = []
    if index_html:
        bases = parse_index_for_bases(index_html)
    # Fallback: synthesize candidates if index not reachable or sparse
    if not bases or len(bases) < 10:
        candidates: List[str] = []
        for year in range(2000, 2025):
            candidates.extend([
                f"{year}_AMC_10",
                f"{year}_AMC_10A",
                f"{year}_AMC_10B",
            ])
        bases = candidates
    entries: List[Entry] = []
    for base in bases:
        # Compose Problems URL
        problems_slug = f"{base}_Problems"
        problems_url = WIKI_BASE + problems_slug

        problems_html = fetch(problems_url)
        if not problems_html:
            # Some years might not have the Problems page at that slug
            m = re.match(r"^(20\d{2})_AMC_10(A|B)?$", base)
            year = int(m.group(1)) if m else 0
            series = f"10{m.group(2) or ''}" if m else "10"
            entries.append(Entry(year, series, base, problems_url, None, "problems_page_missing"))
            continue

        pdf_url = find_pdf_url_from_problems_page(problems_html)
        m = re.match(r"^(20\d{2})_AMC_10(A|B)?$", base)
        year = int(m.group(1)) if m else 0
        series = f"10{m.group(2) or ''}" if m else "10"
        status = "ok" if pdf_url else "pdf_missing"
        entries.append(Entry(year, series, base, problems_url, pdf_url, status))
    return entries


def write_results(entries: List[Entry], out_root: str) -> None:
    csv_path = os.path.join(out_root, "amc10_pdfs.csv")
    json_path = os.path.join(out_root, "amc10_pdfs.json")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "series", "base_slug", "problems_url", "pdf_url", "status"])
        for e in entries:
            w.writerow([e.year, e.series, e.base_slug, e.problems_url, e.pdf_url or "", e.status])
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in entries], f, ensure_ascii=False, indent=2)


def download_pdfs(entries: List[Entry], pdf_dir: str) -> None:
    for e in entries:
        if not e.pdf_url:
            continue
        filename = f"{e.base_slug}_Problems.pdf"  # e.g., 2014_AMC_10B_Problems.pdf
        out_path = os.path.join(pdf_dir, filename)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            continue
        try:
            with requests.get(e.pdf_url, stream=True, timeout=30) as r:
                if r.status_code != 200:
                    continue
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
        except requests.RequestException:
            # Skip on download errors
            continue


def main():
    dirs = ensure_dirs(os.path.join(os.path.dirname(__file__)))
    entries = collect_entries()
    write_results(entries, dirs["root"])
    download_pdfs(entries, dirs["pdfs"])
    # Print a short summary to stdout
    ok = sum(1 for e in entries if e.status == "ok")
    missing_pdf = sum(1 for e in entries if e.status == "pdf_missing")
    missing_page = sum(1 for e in entries if e.status == "problems_page_missing")
    print(f"Total entries: {len(entries)} | PDFs: {ok} | PDF missing: {missing_pdf} | Problems page missing: {missing_page}")
    print(f"CSV: {os.path.join(dirs['root'], 'amc10_pdfs.csv')}")
    print(f"JSON: {os.path.join(dirs['root'], 'amc10_pdfs.json')}")
    print(f"PDFs dir: {dirs['pdfs']}")


if __name__ == "__main__":
    main()
