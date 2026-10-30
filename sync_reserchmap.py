
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

RESEARCHMAP_ID = "fumiyaokazaki"
OUTPUT = Path("_data/researchmap_publications.json")
PAGE_SIZE = 100


def localized(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for lang in ("en", "ja"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def authors_text(value):
    if isinstance(value, dict):
        people = value.get("en") or value.get("ja") or []
    elif isinstance(value, list):
        people = value
    else:
        people = []

    result = []
    for person in people:
        if isinstance(person, str):
            name = person.strip()
        elif isinstance(person, dict):
            name = localized(person.get("name"))
            if not name:
                given = localized(person.get("given_name"))
                family = localized(person.get("family_name"))
                name = " ".join(
                    part for part in (given, family) if part
                )
        else:
            continue

        if name:
            result.append(name)

    return ", ".join(result)


def doi_url(paper):
    identifiers = paper.get("identifiers") or {}
    doi = (
        identifiers.get("doi")
        if isinstance(identifiers, dict)
        else None
    )

    if isinstance(doi, list):
        doi = next(
            (x for x in doi if isinstance(x, str) and x.strip()),
            ""
        )

    if not isinstance(doi, str):
        return ""

    doi = doi.strip()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "doi:",
    ):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break

    return "https://doi.org/" + doi if doi else ""


def arxiv_url(paper):
    for entry in paper.get("see_also") or []:
        url = (
            entry.get("@id", "")
            if isinstance(entry, dict)
            else ""
        )
        if not isinstance(url, str):
            continue

        parsed = urlparse(url)
        if (
            parsed.scheme in ("http", "https")
            and parsed.hostname in (
                "arxiv.org",
                "www.arxiv.org",
                "export.arxiv.org",
            )
        ):
            return "https://" + url.split("://", 1)[1]

    return ""


def fetch_papers():
    records = []

    for start in range(1, 10002, PAGE_SIZE):
        query = urlencode({
            "start": start,
            "limit": PAGE_SIZE,
        })
        url = (
            f"https://api.researchmap.jp/"
            f"{RESEARCHMAP_ID}/published_papers?{query}"
        )

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "researchmap-github-pages-sync/1.0",
            },
        )

        with urlopen(request, timeout=40) as response:
            data = json.load(response)

        items = (
            data.get("items")
            if isinstance(data, dict)
            else None
        )

        if not isinstance(items, list):
            raise RuntimeError(
                f"Unexpected researchmap API response: {url}"
            )

        records.extend(items)

        if len(items) < PAGE_SIZE:
            break
    else:
        raise RuntimeError(
            "Too many publications: pagination limit exceeded"
        )

    if not records:
        raise RuntimeError(
            "researchmap returned no publications; "
            "keeping the existing data"
        )

    return sorted(
        records,
        key=lambda p: str(p.get("publication_date") or ""),
        reverse=True,
    )


def main():
    groups = {
        "peer_reviewed": [],
        "preprints": [],
        "unclassified": [],
    }

    for paper in fetch_papers():
        if not isinstance(paper, dict):
            raise RuntimeError("Unexpected publication record")

        title = localized(paper.get("paper_title"))
        if not title:
            raise RuntimeError(
                "A publication has no readable title"
            )

        date = paper.get("publication_date") or ""

        record = {
            "title": title,
            "authors": authors_text(paper.get("authors")),
            "journal": localized(paper.get("publication_name")),
            "year": str(date)[:4],
            "doi_url": doi_url(paper),
            "arxiv_url": arxiv_url(paper),
        }

        referee = paper.get("referee")

        if referee is True:
            groups["peer_reviewed"].append(record)
        elif referee is False:
            groups["preprints"].append(record)
        else:
            groups["unclassified"].append(record)
            print(f"::warning::referee is unset: {title}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(groups, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "Saved",
        OUTPUT,
        {name: len(items) for name, items in groups.items()},
    )


if __name__ == "__main__":
    main()
