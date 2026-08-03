#!/usr/bin/env python3
"""Validate Markdown contracts without network access or optional packages."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


FENCE_RE = re.compile(r"^\s*```([A-Za-z0-9_-]*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = {"http", "https", "mailto", "ftp"}


def github_slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s", "-", value)


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = github_slug(match.group(2))
        count = counts.get(base, 0)
        anchor = base if count == 0 else f"{base}-{count}"
        counts[base] = count + 1
        anchors.add(anchor)
    return anchors


def parse_fences(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    language: str | None = None
    start_line = 0
    payload: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        match = FENCE_RE.match(line)
        if language is None:
            if match:
                language = match.group(1).lower()
                start_line = line_number
                payload = []
            continue
        if match and not match.group(1):
            if language in {"json", "yaml", "yml"}:
                try:
                    # JSON is a strict YAML subset. Requiring examples in that
                    # subset keeps validation dependency-free and deterministic.
                    json.loads("\n".join(payload))
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"{path}:{start_line}: invalid {language} example: "
                        f"{exc.msg} at example line {exc.lineno}"
                    )
            language = None
            payload = []
            continue
        payload.append(line)
    if language is not None:
        errors.append(f"{path}:{start_line}: unclosed fenced block")
    return errors


def normalize_link_target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1]
    # Optional Markdown link titles are not used by City2 contracts. Supporting
    # a quoted title here prevents it from becoming part of a filesystem path.
    return re.sub(r'''\s+["'][^"']*["']\s*$''', "", raw)


def validate_links(root: Path, path: Path, text: str) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    root = root.resolve()
    for raw in LINK_RE.findall(text):
        target = normalize_link_target(raw)
        parsed = urlsplit(target)
        if parsed.scheme in EXTERNAL_SCHEMES or parsed.netloc:
            continue
        relative = unquote(parsed.path)
        destination = path if not relative else path.parent / relative
        try:
            destination = destination.resolve()
            destination.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"{path}: link escapes repository: {target}")
            continue
        if not destination.exists():
            errors.append(f"{path}: missing local link target: {target}")
            continue
        if parsed.fragment and destination.is_file() and destination.suffix == ".md":
            anchors = anchor_cache.setdefault(
                destination, markdown_anchors(destination.read_text())
            )
            fragment = unquote(parsed.fragment).lower()
            if fragment not in anchors:
                errors.append(f"{path}: missing Markdown anchor: {target}")
    return errors


def validate_markdown(root: Path, path: Path) -> list[str]:
    text = path.read_text()
    errors = parse_fences(path, text)
    errors.extend(validate_links(root, path, text))
    return errors


def tracked_markdown(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "*.md"], cwd=root, text=True
    )
    return [root / item for item in output.splitlines() if item]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    for path in tracked_markdown(root):
        errors.extend(validate_markdown(root, path))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("spec-validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
