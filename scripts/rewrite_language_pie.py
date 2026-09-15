#!/usr/bin/env python3
"""Rebuild the 3d-contrib language pie so 'other' is leftover classified languages.

github-profile-3d-contrib computes:

    other = totalCommitContributions - sum(top 5 languages)

Repos with no primaryLanguage (generated GitHub Pages, Markdown vaults) are
dropped from the language list but still sit in totalCommitContributions, so
they reappear as a dominant 'other' slice. Hidden languages such as HTML
have the same leak.

This script re-aggregates commitContributionsByRepository, omits repos and
languages that should not count, and rebuilds the pie so 'other' is only the
tail of languages that actually classified.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, NamedTuple

PIE_TRANSFORM = 'transform="translate(40, 520)"'
OTHER_NAME = "other"
OTHER_COLOR = "#444444"
PIE_HEIGHT = 200 * 1.3
TOP_N = 5
GRAPHQL_URL = os.environ.get("GITHUB_ENDPOINT", "https://api.github.com/graphql")
ASSETS = Path("profile-3d-contrib")

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      commitContributionsByRepository(maxRepositories: 100) {
        repository {
          name
          primaryLanguage { name color }
        }
        contributions { totalCount }
      }
    }
  }
}
""".strip()


class Slice(NamedTuple):
    language: str
    color: str
    contributions: int


def parse_csv_env(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def d3num(value: float) -> str:
    """Match d3-path's 3-decimal rounding, dropping trailing zeros."""
    rounded = round(value * 1000) / 1000
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def aggregate_languages(
    rows: Iterable[dict],
    exclude_repos: Iterable[str] = (),
    exclude_languages: Iterable[str] = (),
) -> list[Slice]:
    skipped_repos = {name.casefold() for name in exclude_repos}
    skipped_languages = {name.casefold() for name in exclude_languages}
    totals: dict[str, Slice] = {}

    for row in rows:
        repository = row.get("repository") or {}
        repo_name = repository.get("name") or ""
        if repo_name.casefold() in skipped_repos:
            continue
        language = repository.get("primaryLanguage")
        if not language or not language.get("name"):
            continue
        name = language["name"]
        if name.casefold() in skipped_languages:
            continue
        contributions = int((row.get("contributions") or {}).get("totalCount") or 0)
        if contributions <= 0:
            continue
        current = totals.get(name)
        if current:
            totals[name] = Slice(
                language=name,
                color=current.color,
                contributions=current.contributions + contributions,
            )
        else:
            totals[name] = Slice(
                language=name,
                color=language.get("color") or OTHER_COLOR,
                contributions=contributions,
            )

    return sorted(totals.values(), key=lambda item: (-item.contributions, item.language))


def pie_slices(languages: list[Slice], top_n: int = TOP_N) -> list[Slice]:
    head = languages[:top_n]
    tail = languages[top_n:]
    remainder = sum(item.contributions for item in tail)
    if remainder > 0:
        head.append(Slice(OTHER_NAME, OTHER_COLOR, remainder))
    return [item for item in head if item.contributions > 0]


def _point(angle: float, radius: float) -> tuple[float, float]:
    # d3.arc treats angle 0 as 12 o'clock.
    return (math.cos(angle - math.pi / 2) * radius, math.sin(angle - math.pi / 2) * radius)


def donut_path(start: float, end: float, inner: float, outer: float) -> str:
    span = end - start
    if span <= 0:
        return ""
    two_pi = math.pi * 2
    if span >= two_pi - 1e-8:
        mid = start + math.pi
        return donut_path(start, mid, inner, outer)[:-1] + donut_path(
            mid, start + two_pi, inner, outer
        )[1:]

    large = 1 if span > math.pi else 0
    sx, sy = _point(start, outer)
    ex, ey = _point(end, outer)
    ix, iy = _point(end, inner)
    jx, jy = _point(start, inner)
    return (
        f"M{d3num(sx)},{d3num(sy)}"
        f"A{d3num(outer)},{d3num(outer)},0,{large},1,{d3num(ex)},{d3num(ey)}"
        f"L{d3num(ix)},{d3num(iy)}"
        f"A{d3num(inner)},{d3num(inner)},0,{large},0,{d3num(jx)},{d3num(jy)}"
        "Z"
    )


def _opacity_values(index: int, count: int) -> str:
    steps = 5
    length = count + steps
    values = []
    for position in range(length):
        if position < index:
            values.append("0")
            continue
        amount = min((position - index) / steps, 1)
        if amount <= 0:
            values.append("0")
        elif amount >= 1:
            values.append("1")
        else:
            values.append(str(amount))
    return ";".join(values)


def _animate(attribute: str, index: int, count: int) -> str:
    return (
        f'<animate attributeName="{attribute}" values="{_opacity_values(index, count)}" '
        'dur="3s" repeatCount="1"></animate>'
    )


def render_pie_group(slices: list[Slice], animated: bool) -> str:
    height = PIE_HEIGHT
    radius = height / 2
    margin = radius / 10
    inner = radius / 2
    outer = radius - margin
    row = 8
    font_size = height / row / 1.5
    offset = (row - len(slices)) / 2 + 0.5
    total = sum(item.contributions for item in slices) or 1
    legend_x = radius * 2.1

    legend_marks = []
    legend_labels = []
    paths = []
    angle = 0.0
    for index, item in enumerate(slices):
        span = item.contributions / total * math.pi * 2
        path = donut_path(angle, angle + span, inner, outer)
        angle += span
        y_text = (index + offset) * (height / row)
        y_rect = y_text - font_size / 2
        anim = _animate("fill-opacity", index, len(slices)) if animated else ""
        legend_marks.append(
            f'<rect x="0" y="{y_rect}" width="{font_size}" height="{font_size}" '
            f'fill="{item.color}" class="stroke-bg" stroke-width="1px">{anim}</rect>'
        )
        legend_labels.append(
            f'<text dominant-baseline="middle" x="{d3num(font_size * 1.2)}" y="{y_text}" '
            f'class="fill-fg" font-size="{font_size}px">{item.language}{anim}</text>'
        )
        paths.append(
            f'<path d="{path}" style="fill: {item.color};" class="stroke-bg" '
            f'stroke-width="2px"><title>{item.language} {item.contributions}</title>'
            f"{anim}</path>"
        )

    return (
        f'<g {PIE_TRANSFORM}>'
        f'<g transform="translate({d3num(legend_x)}, 0)">'
        + "".join(legend_marks)
        + "".join(legend_labels)
        + "</g>"
        f'<g transform="translate({d3num(radius)}, {d3num(radius)})">'
        + "".join(paths)
        + "</g></g>"
    )


def replace_pie_group(svg: str, group: str) -> str:
    marker = f"<g {PIE_TRANSFORM}>"
    start = svg.find(marker)
    if start < 0:
        raise ValueError("language pie group not found")
    depth = 0
    index = start
    while index < len(svg):
        open_tag = svg.find("<g", index)
        close_tag = svg.find("</g>", index)
        if close_tag < 0:
            break
        if open_tag >= 0 and open_tag < close_tag:
            depth += 1
            index = open_tag + 2
            continue
        depth -= 1
        end = close_tag + len("</g>")
        if depth == 0:
            return svg[:start] + group + svg[end:]
        index = end
    raise ValueError("language pie group is not well-formed")


def pie_is_animated(svg: str) -> bool:
    marker = f"<g {PIE_TRANSFORM}>"
    start = svg.find(marker)
    if start < 0:
        return False
    preview = svg[start : start + 4000]
    return "<animate" in preview


def fetch_contribution_rows(token: str, username: str) -> list[dict]:
    payload = json.dumps({"query": QUERY, "variables": {"login": username}}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "edxi-profile-language-pie",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    if body.get("errors"):
        raise RuntimeError(body["errors"][0].get("message", "GraphQL error"))
    collection = body["data"]["user"]["contributionsCollection"]
    return collection["commitContributionsByRepository"]


def slices_from_existing_svg(svg: str) -> list[Slice]:
    """Fallback: keep named slices from the current pie and drop 'other'."""
    start = svg.find(f"<g {PIE_TRANSFORM}>")
    if start < 0:
        return []
    chunk = svg[start : start + 6000]
    titles = re.findall(r"<title>([^<]+) (\d+)</title>", chunk)
    colors = re.findall(
        r'style="fill: ([^;]+);"[^>]*>\s*<title>([^<]+) \d+</title>',
        chunk,
    )
    color_by_name = {name: color for color, name in colors}
    return [
        Slice(name, color_by_name.get(name, OTHER_COLOR), int(count))
        for name, count in titles
        if name.casefold() != OTHER_NAME
    ]


def rewrite_assets(slices: list[Slice]) -> list[str]:
    rewritten = []
    for path in sorted(ASSETS.glob("*.svg")):
        original = path.read_text(encoding="utf-8")
        if f"<g {PIE_TRANSFORM}>" not in original:
            continue
        group = render_pie_group(slices, pie_is_animated(original))
        path.write_text(replace_pie_group(original, group), encoding="utf-8")
        rewritten.append(path.name)
    return rewritten


def main() -> int:
    exclude_repos = parse_csv_env("EXCLUDE_REPOS")
    exclude_languages = parse_csv_env("EXCLUDE_LANGUAGES")
    username = os.environ.get("USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("GITHUB_TOKEN", "")

    slices: list[Slice] = []
    source = "graphql"
    if token and username:
        try:
            rows = fetch_contribution_rows(token, username)
            slices = pie_slices(
                aggregate_languages(rows, exclude_repos, exclude_languages)
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError) as exc:
            print(f"GraphQL language fetch failed ({exc}); falling back to SVG titles.")
            source = "svg-fallback"
    else:
        source = "svg-fallback"

    if source == "svg-fallback":
        sample = ASSETS / "profile-gitblock.svg"
        slices = pie_slices(slices_from_existing_svg(sample.read_text(encoding="utf-8")))

    if not slices:
        print("No classified languages to draw; leaving pies unchanged.")
        return 0

    rewritten = rewrite_assets(slices)
    summary = ", ".join(f"{item.language} {item.contributions}" for item in slices)
    print(f"Rewrote {len(rewritten)} pies from {source}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
