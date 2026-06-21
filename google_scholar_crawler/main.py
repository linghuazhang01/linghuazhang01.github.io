import json
import logging
import os
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)
SCHOLAR_BASE_URL = "https://scholar.google.com/citations"
USER_AGENT = (
    "Mozilla/5.0 (compatible; citation-updater/1.0; "
    "+https://linghuazhang01.github.io)"
)
REQUEST_TIMEOUT_SECONDS = 30


def clean_html(raw_html: str) -> str:
    """Convert a small HTML fragment to plain text."""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return unescape(text).replace("\xa0", " ").strip()


def extract_first(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.DOTALL)
    return clean_html(match.group(1)) if match else default


def fetch_profile_html(scholar_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", scholar_id):
        raise ValueError("GOOGLE_SCHOLAR_ID contains unexpected characters.")

    query = urlencode({"user": scholar_id, "hl": "en"})
    request = Request(
        f"{SCHOLAR_BASE_URL}?{query}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_publications(profile_html: str) -> dict[str, dict[str, object]]:
    publications: dict[str, dict[str, object]] = {}
    rows = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', profile_html, re.DOTALL)

    for row in rows:
        paper_id = extract_first(r"citation_for_view=([^\"&]+)", row)
        title = extract_first(r'<a [^>]*class="gsc_a_at"[^>]*>(.*?)</a>', row)
        if not paper_id or not title:
            continue

        gray_lines = [
            clean_html(line)
            for line in re.findall(r'<div class="gs_gray">(.*?)</div>', row, re.DOTALL)
        ]
        citation_cell = extract_first(r'<td class="gsc_a_c"[^>]*>(.*?)</td>', row, "0")
        year = extract_first(r'<td class="gsc_a_y"[^>]*>(.*?)</td>', row)
        citation_match = re.search(r"\d+", citation_cell)

        publications[paper_id] = {
            "author_pub_id": paper_id,
            "num_citations": int(citation_match.group(0)) if citation_match else 0,
            "bib": {
                "title": title,
                "author": gray_lines[0] if gray_lines else "",
                "citation": gray_lines[1] if len(gray_lines) > 1 else "",
                "pub_year": year,
            },
        }

    return publications


def parse_profile(profile_html: str) -> dict[str, object]:
    name = extract_first(r'<div id="gsc_prf_in">(.*?)</div>', profile_html)
    citation_counts = re.findall(r'<td class="gsc_rsb_std">(\d+)</td>', profile_html)
    publications = parse_publications(profile_html)

    if not name:
        raise RuntimeError("Could not find Google Scholar profile name.")

    return {
        "name": name,
        "citedby": int(citation_counts[0]) if citation_counts else 0,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "publications": publications,
    }


def write_results(author: dict[str, object]) -> None:
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    (results_dir / "gs_data.json").write_text(
        json.dumps(author, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (results_dir / "gs_data_shieldsio.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "label": "citations",
                "message": str(author["citedby"]),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    scholar_id = os.environ.get("GOOGLE_SCHOLAR_ID", "").strip()
    if not scholar_id:
        raise SystemExit("GOOGLE_SCHOLAR_ID is not configured.")

    profile_html = fetch_profile_html(scholar_id)
    author = parse_profile(profile_html)
    write_results(author)
    LOGGER.info(
        "Updated citation data for %s: %s citations, %s publications.",
        author["name"],
        author["citedby"],
        len(author["publications"]),
    )


if __name__ == "__main__":
    main()
