#!/usr/bin/env python3
"""Validate local links, assets, and anchors in the public HTML docs."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "javascript:", "data:")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        for key in ("href", "src"):
            if values.get(key):
                self.urls.append(str(values[key]))


def main() -> int:
    pages: dict[Path, PageParser] = {}
    for path in sorted(DOCS_ROOT.glob("*.html")):
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path.resolve()] = parser

    if not pages:
        raise SystemExit("No public HTML docs found")

    errors: list[str] = []
    for source, parser in pages.items():
        for url in parser.urls:
            if url.startswith(EXTERNAL_SCHEMES):
                continue
            parts = urlsplit(url)
            target = (source.parent / (parts.path or source.name)).resolve()
            if not target.exists():
                errors.append(f"{source.name}: missing {url}")
                continue
            if parts.fragment and target.suffix == ".html":
                target_parser = pages.get(target)
                if target_parser is None or parts.fragment not in target_parser.ids:
                    errors.append(f"{source.name}: missing anchor {url}")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"Validated links, assets, and anchors across {len(pages)} HTML pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
