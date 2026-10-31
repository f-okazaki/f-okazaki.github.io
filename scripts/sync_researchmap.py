"""Fetch publications and CV together; uses only the Python standard library."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

RESEARCHMAP_ID = "fumiyaokazaki"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data"
PAGE_SIZE = 100

CV_SECTIONS = {
    "education": (
        "Education", ("affiliation", "department", "course"),
    ),
    "research_experience": (
        "Work Experience", ("job", "affiliation", "section"),
    ),
    "teaching_experience": (
        "Teaching", ("subject_name", "institution_name"),
    ),
    "association_memberships": (
        "Professional Memberships", ("academic_society_name",),
    ),
    "research_projects": (
        "Research Grants",
        ("research_project_title", "offer_organization", "system_name",
         "category", "institution_name"),
    ),
}


def text(value, languages=("en", "ja")):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for language in languages:
            result = value.get(language)
            if isinstance(result, str) and result.strip():
                return result.strip()
    return ""


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def fetch_all(kind):
    """Reject API errors, incomplete results and repeated pages."""
    records, seen = [], set()
    expected = None

    for _ in range(100):
        query = urlencode({"start": len(records) + 1, "limit": PAGE_SIZE})
        url = f"https://api.researchmap.jp/{RESEARCHMAP_ID}/{kind}?{query}"
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "researchmap-pages-sync/1.0",
        })

        try:
            with urlopen(request, timeout=40) as response:
                data = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"{kind}: request failed: {exc}") from exc

        if not isinstance(data, dict) or data.get("error"):
            raise RuntimeError(f"{kind}: API returned an error or invalid data")

        total = data.get("total_items")
        if total is not None:
            total = int(total)
            if total < 0 or (expected is not None and total != expected):
                raise RuntimeError(f"{kind}: inconsistent total_items; retry sync")
            expected = total

        items = data.get("items")
        if items is None and expected == 0:
            items = []
        if not isinstance(items, list):
            raise RuntimeError(f"{kind}: missing or invalid items")

        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(f"{kind}: invalid record")
            identity = str(item.get("rm:id") or item.get("@id") or
                           json.dumps(item, sort_keys=True, ensure_ascii=False))
            if identity in seen:
                raise RuntimeError(f"{kind}: repeated record; retry sync")
            seen.add(identity)
            records.append(item)

        time.sleep(0.5)
        if expected is not None:
            if len(records) == expected:
                return records
            if len(records) > expected or not items:
                raise RuntimeError(f"{kind}: incomplete or inconsistent response")
        elif len(items) < PAGE_SIZE:
            return records

    raise RuntimeError(f"{kind}: pagination limit exceeded")


def authors_text(value):
    if isinstance(value, dict):
        value = value.get("en") or value.get("ja") or []
    names = []
    for person in as_list(value):
        if isinstance(person, dict):
            name = text(person.get("name"))
            if not name:
                name = " ".join(filter(None, (
                    text(person.get("given_name")),
                    text(person.get("family_name")),
                )))
        else:
            name = text(person)
        if name:
            names.append(name)
    return ", ".join(names)


def identifiers(item, key):
    values = item.get("identifiers") or {}
    if not isinstance(values, dict):
        return []
    return [str(v).strip() for v in as_list(values.get(key))
            if isinstance(v, (str, int)) and str(v).strip()]


def doi_url(paper):
    values = identifiers(paper, "doi")
    if not values:
        return ""
    doi = values[0]
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):].strip()
            break
    return "https://doi.org/" + doi if doi else ""


def arxiv_url(paper):
    for entry in as_list(paper.get("see_also")):
        url = text(entry.get("@id")) if isinstance(entry, dict) else ""
        try:
            parsed = urlparse(url)
            if (parsed.scheme in ("http", "https")
                    and parsed.hostname in ("arxiv.org", "www.arxiv.org",
                                            "export.arxiv.org")
                    and not parsed.username):
                return parsed._replace(scheme="https").geturl()
        except ValueError:
            continue
    return ""


def make_publications(papers):
    if not papers:
        raise RuntimeError("No publications returned; keeping the saved data")
    groups = {"peer_reviewed": [], "preprints": []}
    papers = sorted(papers, key=lambda p: (
        str(p.get("publication_date") or ""), str(p.get("rm:id") or "")
    ), reverse=True)

    for paper in papers:
        title = text(paper.get("paper_title"))
        if not title:
            raise RuntimeError("A publication has no readable title")
        record = {
            "title": title,
            "authors": authors_text(paper.get("authors")),
            "journal": text(paper.get("publication_name")),
            "year": str(paper.get("publication_date") or "")[:4],
            "doi_url": doi_url(paper),
            "arxiv_url": arxiv_url(paper),
        }
        # Only literal true is peer-reviewed; false/null/missing -> Preprints.
        group = "peer_reviewed" if paper.get("referee") is True else "preprints"
        groups[group].append(record)
    return groups


def display_date(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if value.startswith("9999"):
        return "Present"
    parts = value.split("-")
    if len(parts[0]) != 4 or not parts[0].isdigit():
        raise ValueError(f"Unexpected date: {value!r}")
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    if len(parts) > 1 and parts[1].isdigit():
        month = int(parts[1])
        if 1 <= month <= 12:
            return f"{months[month - 1]} {parts[0]}"
    return parts[0]


def period(item):
    start = display_date(item.get("from_date"))
    end = display_date(item.get("to_date"))
    if start and end:
        return start if start == end else f"{start} – {end}"
    if start:
        return f"From {start}"
    return (end if end == "Present" else f"Until {end}") if end else ""


def make_cv_item(item, kind, fields):
    parts, missing = [], []
    for field in fields:
        value = item.get(field)
        english = text(value, ("en",))
        if english and english not in parts:
            parts.append(english)
        if isinstance(value, dict) and any(value.values()) and not english:
            missing.append(field)

    source = f"https://researchmap.jp/{RESEARCHMAP_ID}/{kind}"
    if item.get("rm:id") is not None:
        source += "/" + quote(str(item["rm:id"]), safe="")
    if missing:
        print(f"Missing English: {kind}: {', '.join(missing)}")
    return {
        "period": period(item),
        "text": ", ".join(parts) or
                "English details are not registered on researchmap.",
        "grant_number": ", ".join(identifiers(item, "grant_number")),
        "source_url": source,
        "missing_english": missing,
    }


def main():
    # Fetch and validate everything before touching either saved JSON file.
    publications = make_publications(fetch_all("published_papers"))
    sections = []
    for kind, (heading, fields) in CV_SECTIONS.items():
        records = fetch_all(kind)
        records.sort(key=lambda item: (
            str(item.get("from_date") or ""),
            str(item.get("to_date") or ""),
            str(item.get("rm:id") or ""),
        ), reverse=True)
        sections.append({
            "title": heading,
            "items": [make_cv_item(item, kind, fields) for item in records],
        })
        print(f"{heading}: {len(records)} records")

    outputs = {
        "researchmap_publications.json": publications,
        "researchmap_cv.json": {"sections": sections},
    }
    contents = {
        name: json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        for name, data in outputs.items()
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        path = DATA_DIR / name
        if path.exists() and path.read_text(encoding="utf-8") == content:
            print(f"Unchanged: {name}")
            continue
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        print(f"Saved: {name}")

    print("Publications:", {k: len(v) for k, v in publications.items()})


if __name__ == "__main__":
    main()
