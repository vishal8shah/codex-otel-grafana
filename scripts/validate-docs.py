#!/usr/bin/env python3
"""Validate local links, assets, and anchors in the public HTML docs."""

from __future__ import annotations

import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "javascript:", "data:")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED_WALKTHROUGH_SIZE = (1280, 720)
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}
UNSAFE_PNG_MARKERS = (
    b"conversation_id",
    b"call_id",
    b"user_email",
    b"user_account_id",
    b"api_key",
    b"authorization",
    b"bearer",
    b"password",
    b"secret",
    b"c:\\",
    b"/users/",
)
FORBIDDEN_PUBLIC_CLAIMS = (
    "codex observability platform",
    "observability platform",
    "monitoring platform",
    "production observability",
    "production monitoring",
    "full codex observability",
    "complete codex observability",
    "complete coverage",
    "tracks all codex behaviour",
    "tracks all codex behavior",
    "proves codex is healthy",
    "proves a codex bug",
    "automatic root cause",
    "root cause automatically found",
)


def validate_walkthrough_png(path: Path) -> list[str]:
    """Validate screenshot structure only; visual privacy review remains manual."""
    errors: list[str] = []
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        return [f"{path.name}: invalid PNG signature"]

    position = len(PNG_SIGNATURE)
    chunks: list[bytes] = []
    width: int | None = None
    height: int | None = None
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_end = position + 12 + length
        if chunk_end > len(data):
            errors.append(f"{path.name}: truncated PNG chunk {chunk_type!r}")
            break
        chunks.append(chunk_type)
        if chunk_type == b"IHDR":
            if length < 8:
                errors.append(f"{path.name}: invalid IHDR chunk")
            else:
                width, height = struct.unpack(">II", data[position + 8 : position + 16])
        position = chunk_end
        if chunk_type == b"IEND":
            break

    if not chunks or chunks[0] != b"IHDR":
        errors.append(f"{path.name}: IHDR is missing or not the first PNG chunk")
    if b"IEND" not in chunks:
        errors.append(f"{path.name}: IEND chunk is missing")
    if (width, height) != EXPECTED_WALKTHROUGH_SIZE:
        errors.append(
            f"{path.name}: expected {EXPECTED_WALKTHROUGH_SIZE[0]}x"
            f"{EXPECTED_WALKTHROUGH_SIZE[1]}, found {width}x{height}"
        )
    for chunk_type in sorted(PNG_TEXT_CHUNKS.intersection(chunks)):
        errors.append(f"{path.name}: forbidden PNG text metadata chunk {chunk_type.decode()}")

    lowered = data.lower()
    for marker in UNSAFE_PNG_MARKERS:
        if marker in lowered:
            errors.append(f"{path.name}: unsafe raw-byte marker {marker.decode(errors='replace')}")
    return errors


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.urls: list[str] = []
        self.external_assets: list[str] = []
        self.images: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        for key in ("href", "src"):
            if values.get(key):
                self.urls.append(str(values[key]))
        src = str(values.get("src") or "")
        href = str(values.get("href") or "")
        rel = str(values.get("rel") or "").lower().split()
        if src.startswith(("http://", "https://")):
            self.external_assets.append(src)
        if tag == "img" and src:
            self.images.append((src, str(values.get("alt") or "")))
        if tag == "link" and "stylesheet" in rel and href.startswith(("http://", "https://")):
            self.external_assets.append(href)


def main() -> int:
    pages: dict[Path, PageParser] = {}
    for path in sorted(DOCS_ROOT.glob("*.html")):
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path.resolve()] = parser

    if not pages:
        raise SystemExit("No public HTML docs found")

    errors: list[str] = []

    onboarding_path = DOCS_ROOT / "onboarding.html"
    if onboarding_path.resolve() not in pages:
        errors.append("onboarding.html: required onboarding page is missing")
    else:
        onboarding_text = onboarding_path.read_text(encoding="utf-8").lower()
        required_markers = (
            "py --version",
            ".\\scripts\\preflight.ps1",
            "python scripts/health-check.py",
            "python scripts/run-onboarding-demo.py",
            ".\\scripts\\start.ps1",
            ".\\scripts\\stop.ps1",
            "log_user_prompt=false",
            "synthetic onboarding data only",
        )
        for marker in required_markers:
            if marker not in onboarding_text:
                errors.append(f"onboarding.html: required onboarding marker is missing: {marker}")
        for forbidden_default in ("--host 0.0.0.0", "dev_webhook_listener.py", "watch-stuck"):
            if forbidden_default in onboarding_text:
                errors.append(f"onboarding.html: Phase 6 notification command entered the default onboarding path: {forbidden_default}")

    for source in pages:
        page_text = source.read_text(encoding="utf-8").lower()
        if 'href="onboarding.html"' not in page_text or ">03</span>onboarding" not in page_text:
            errors.append(f"{source.name}: primary Onboarding navigation link is missing")

    readme_path = REPO_ROOT / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8").lower()
    if "docs/onboarding.html" not in readme_text:
        errors.append("README.md: onboarding entry point is missing")
    for relative in (
        "scripts/preflight.py",
        "scripts/preflight.ps1",
        "scripts/health-check.py",
        "scripts/run-onboarding-demo.py",
        "scripts/emit-demo-scenarios.py",
    ):
        if not (REPO_ROOT / relative).is_file():
            errors.append(f"onboarding command target is missing: {relative}")
    for source, parser in pages.items():
        for url in parser.external_assets:
            errors.append(f"{source.name}: external asset dependency {url}")
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

        text = source.read_text(encoding="utf-8").lower()
        for banned in ("fonts.googleapis.com", "fonts.gstatic.com", "mermaid.min.js", "cdn.jsdelivr.net"):
            if banned in text:
                errors.append(f"{source.name}: forbidden external dependency marker {banned}")
        for claim in FORBIDDEN_PUBLIC_CLAIMS:
            if claim in text:
                errors.append(f"{source.name}: forbidden public claim {claim}")

    css_path = DOCS_ROOT / "assets" / "site.css"
    css_text = css_path.read_text(encoding="utf-8").lower()
    if "url(http://" in css_text or "url(https://" in css_text:
        errors.append("assets/site.css: remote asset URL")

    walkthrough_dir = DOCS_ROOT / "assets" / "dashboard-walkthrough"
    walkthrough_images = sorted(walkthrough_dir.glob("*.png"))
    referenced: dict[str, tuple[Path, str]] = {}
    for source, parser in pages.items():
        for src, alt in parser.images:
            if src.startswith("assets/dashboard-walkthrough/"):
                referenced[Path(src).name] = (source, alt)

    for image in walkthrough_images:
        errors.extend(validate_walkthrough_png(image))
        if image.name not in referenced:
            errors.append(f"{image.name}: walkthrough screenshot is not referenced")
            continue
        source, alt = referenced[image.name]
        if "synthetic example data" not in alt.lower():
            errors.append(f"{source.name}: {image.name} alt text lacks synthetic example data")
        source_text = source.read_text(encoding="utf-8")
        marker = f'assets/dashboard-walkthrough/{image.name}'
        position = source_text.find(marker)
        nearby = source_text[max(0, position - 500) : position + 500].lower()
        if "synthetic example data" not in nearby:
            errors.append(f"{source.name}: {image.name} lacks a visible nearby synthetic label")

    missing_assets = sorted(set(referenced) - {path.name for path in walkthrough_images})
    for name in missing_assets:
        errors.append(f"walkthrough screenshot asset missing: {name}")

    review_path = DOCS_ROOT / "dashboard-walkthrough-privacy-review.md"
    if walkthrough_images:
        if not review_path.exists():
            errors.append("dashboard walkthrough privacy review log is missing")
        else:
            review_text = review_path.read_text(encoding="utf-8")
            for image in walkthrough_images:
                if image.name not in review_text:
                    errors.append(f"privacy review log is missing {image.name}")
            if review_text.count("Reviewer/check status: reviewed") != len(walkthrough_images):
                errors.append("privacy review log does not contain one reviewed status per screenshot")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"Validated links, assets, and anchors across {len(pages)} HTML pages")
    if walkthrough_images:
        print(
            f"Validated {len(walkthrough_images)} walkthrough PNG files: signatures, "
            "1280x720 dimensions, no text metadata chunks, and no unsafe raw-byte markers"
        )
        print("Screenshot pixel/content privacy remains covered by the manual review log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
