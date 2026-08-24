#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import string
import xml.etree.ElementTree as ET
from pathlib import Path


REQUIRED_SECTIONS = (
    "## Current practice",
    "## Selected work",
    "## Activity",
    "## Practice areas",
)
SELECTED_WORK_LINK_TOKENS = (
    "[OpenClaw dispatch skills]"
    "(https://github.com/edxi/openclaw-dispatch-skills)",
    "[VMware ChatOps](https://github.com/edxi/Poshbot.VMware)",
)
LOCAL_IMAGE_TOKEN = (
    "![GitHub contribution calendar](assets/contribution-calendar.svg)"
)
BANNED_COMPONENTS = (
    "github-profile-trophy",
    "komarev.com/ghpvc",
    "github-readme-stats",
    "github-readme-streak",
    "top-langs",
    "platane/snk",
    "visitor badge",
)
BANNED_HEADINGS = (
    "## Blog",
    "## Website",
    "## Writing",
    "## Articles",
)
BACKSLASH_ESCAPED_PUNCTUATION = re.compile(
    r"\\([" + re.escape(string.punctuation) + r"])"
)
ALTERNATE_LINK_SOURCE = re.compile(
    r"\["
    r"|https?://"
    r"|<\s*/?\s*a\b"
    r"|<(?:[a-z][a-z0-9+.-]{1,31}:[^<>\s]*|[^<>\s]+@[^<>\s]+)>",
    flags=re.IGNORECASE,
)
ALTERNATE_IMAGE_SOURCE = re.compile(
    r"!\s*\[|<\s*/?\s*img\b",
    flags=re.IGNORECASE,
)
FENCE_OPENING = re.compile(r" {0,3}(`{3,}|~{3,})")
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", flags=re.DOTALL)
INLINE_CODE_SPAN = re.compile(
    r"(?<!`)(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`)",
    flags=re.DOTALL,
)


def _section(text: str, start_heading: str, end_heading: str) -> str:
    start = re.search(
        rf"^{re.escape(start_heading)}$",
        text,
        flags=re.MULTILINE,
    )
    if start is None:
        return ""
    end = re.search(
        rf"^{re.escape(end_heading)}$",
        text[start.end() :],
        flags=re.MULTILINE,
    )
    if end is None:
        return ""
    return text[start.start() : start.end() + end.start()]


def _mask_inactive_source(text: str) -> str:
    masked = list(text)

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if masked[position] not in "\r\n":
                masked[position] = " "

    for comment in HTML_COMMENT.finditer(text):
        mask(*comment.span())

    source_without_comments = "".join(masked)
    fence_character = ""
    fence_length = 0
    offset = 0
    for line in source_without_comments.splitlines(keepends=True):
        line_body = line.rstrip("\r\n")
        line_end = offset + len(line)
        if fence_character:
            mask(offset, line_end)
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}"
                rf"{{{fence_length},}}[ \t]*",
                line_body,
            )
            if closing:
                fence_character = ""
                fence_length = 0
            offset = line_end
            continue

        opening = FENCE_OPENING.match(line_body)
        if opening:
            fence = opening.group(1)
            fence_character = fence[0]
            fence_length = len(fence)
            mask(offset, line_end)
        offset = line_end

    source_without_blocks = "".join(masked)
    for code_span in INLINE_CODE_SPAN.finditer(source_without_blocks):
        mask(*code_span.span())
    return "".join(masked)


def _mask_tokens(text: str, tokens: tuple[str, ...]) -> str:
    for token in tokens:
        text = text.replace(token, " " * len(token))
    return text


def _normalize_alternate_source(text: str) -> str:
    decoded = html.unescape(text)
    return BACKSLASH_ESCAPED_PUNCTUATION.sub(r"\1", decoded)


def _has_alternate_link_source(text: str) -> bool:
    remainder = _mask_tokens(
        text,
        (*SELECTED_WORK_LINK_TOKENS, LOCAL_IMAGE_TOKEN),
    )
    return bool(ALTERNATE_LINK_SOURCE.search(_normalize_alternate_source(remainder)))


def _has_alternate_image_source(text: str) -> bool:
    remainder = _mask_tokens(text, (LOCAL_IMAGE_TOKEN,))
    return bool(
        ALTERNATE_IMAGE_SOURCE.search(_normalize_alternate_source(remainder))
    )


def _has_canonical_selected_work(text: str, selected_text: str) -> bool:
    if any(text.count(token) != 1 for token in SELECTED_WORK_LINK_TOKENS):
        return False

    positions: list[int] = []
    for token in SELECTED_WORK_LINK_TOKENS:
        position = selected_text.find(token)
        if position == -1:
            return False
        if position > 0 and selected_text[position - 1] in "\\!":
            return False
        positions.append(position)
    return positions == sorted(positions)


def _has_canonical_image(text: str, activity_text: str) -> bool:
    if text.count(LOCAL_IMAGE_TOKEN) != 1:
        return False
    position = activity_text.find(LOCAL_IMAGE_TOKEN)
    if position == -1:
        return False
    return position == 0 or activity_text[position - 1] != "\\"


def validate_readme(text: str) -> list[str]:
    errors: list[str] = []
    active_source = _mask_inactive_source(text)
    headings = re.findall(r"^## .+$", active_source, flags=re.MULTILINE)
    if tuple(headings) != REQUIRED_SECTIONS:
        errors.append("README section contract is invalid")

    lowered = text.lower()
    for component in BANNED_COMPONENTS:
        if component in lowered:
            errors.append(f"banned component found: {component}")
    for heading in BANNED_HEADINGS:
        if heading in text:
            errors.append(f"banned section found: {heading}")

    activity_text = _section(
        active_source,
        REQUIRED_SECTIONS[2],
        REQUIRED_SECTIONS[3],
    )
    if (
        not _has_canonical_image(text, activity_text)
        or _has_alternate_image_source(text)
    ):
        errors.append("README must contain exactly one local image")

    selected_text = _section(
        active_source,
        REQUIRED_SECTIONS[1],
        REQUIRED_SECTIONS[2],
    )
    if (
        not _has_canonical_selected_work(text, selected_text)
        or _has_alternate_link_source(selected_text)
    ):
        errors.append("selected-work links must be exactly the two approved links")

    if _has_alternate_link_source(text):
        errors.append("README links must be exactly the two selected-work links")
    return errors


def validate_svg(path: Path) -> list[str]:
    if not path.is_file() or path.stat().st_size == 0:
        return [f"SVG is missing or empty: {path}"]
    try:
        root = ET.parse(path).getroot()
    except OSError:
        return [f"SVG cannot be read: {path}"]
    except (ET.ParseError, UnicodeError) as error:
        return [f"SVG is not well formed: {error}"]
    if root.tag.rsplit("}", 1)[-1] != "svg":
        return [f"SVG root element is invalid: {root.tag}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        readme = arguments.readme.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors = [f"README cannot be read: {arguments.readme}"]
    else:
        errors = validate_readme(readme)
    errors.extend(validate_svg(arguments.svg))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("profile validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
