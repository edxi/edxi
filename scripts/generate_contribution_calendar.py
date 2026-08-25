#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query ContributionCalendar($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            weekday
          }
        }
      }
    }
  }
}
"""
LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}


def fetch_contribution_calendar(
    username: str,
    token: str,
    *,
    endpoint: str = GRAPHQL_ENDPOINT,
) -> dict[str, Any]:
    if not username.strip():
        raise ValueError("GitHub username is required")
    if not token.strip():
        raise ValueError("GitHub token is required")
    body = json.dumps(
        {
            "query": GRAPHQL_QUERY,
            "variables": {"login": username},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "edxi-profile-contribution-calendar",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"GitHub contribution query failed: {error}") from error
    if payload.get("errors"):
        messages = "; ".join(
            str(item.get("message", "unknown GraphQL error"))
            for item in payload["errors"]
        )
        raise RuntimeError(f"GitHub contribution query failed: {messages}")
    try:
        calendar = payload["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]
    except (KeyError, TypeError) as error:
        raise RuntimeError("GitHub contribution response is incomplete") from error
    if not isinstance(calendar, dict):
        raise RuntimeError("GitHub contribution response has no calendar")
    return calendar


def _calendar_days(calendar: dict[str, Any]) -> tuple[list[list[dict[str, Any]]], list[date]]:
    if not isinstance(calendar, dict):
        raise ValueError("contribution calendar must be an object")
    weeks = calendar.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        raise ValueError("contribution calendar must contain weeks")

    normalized: list[list[dict[str, Any]]] = []
    dates: list[date] = []
    seen: set[date] = set()
    for week in weeks:
        if not isinstance(week, dict):
            raise ValueError("contribution week must be an object")
        days = week.get("contributionDays")
        if not isinstance(days, list) or not days:
            raise ValueError("contribution week must contain days")
        normalized_week: list[dict[str, Any]] = []
        for day in days:
            if not isinstance(day, dict):
                raise ValueError("contribution day must be an object")
            try:
                parsed_date = date.fromisoformat(day["date"])
                count = day["contributionCount"]
                level = day["contributionLevel"]
                weekday = day["weekday"]
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("contribution day is incomplete") from error
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                or level not in LEVELS
                or isinstance(weekday, bool)
                or not isinstance(weekday, int)
                or not 0 <= weekday <= 6
                or parsed_date in seen
            ):
                raise ValueError("contribution day is invalid")
            seen.add(parsed_date)
            dates.append(parsed_date)
            normalized_week.append(
                {
                    "date": parsed_date.isoformat(),
                    "level": LEVELS[level],
                    "weekday": weekday,
                }
            )
        normalized.append(normalized_week)
    if dates != sorted(dates):
        raise ValueError("contribution days must be chronological")
    return normalized, dates


def render_calendar(calendar: dict[str, Any], username: str) -> str:
    if not username.strip():
        raise ValueError("GitHub username is required")
    weeks, dates = _calendar_days(calendar)
    cell = 10
    gap = 3
    step = cell + gap
    padding = 16
    panel_gap = 18
    columns = max(8, math.ceil(len(weeks) / 2))
    panels = math.ceil(len(weeks) / columns)
    panel_height = 7 * step - gap
    width = padding * 2 + columns * step - gap
    height = padding * 2 + panels * panel_height + (panels - 1) * panel_gap

    day_rectangles: list[str] = []
    for week_index, week in enumerate(weeks):
        panel = week_index // columns
        column = week_index % columns
        x = padding + column * step
        panel_y = padding + panel * (panel_height + panel_gap)
        for day in week:
            y = panel_y + day["weekday"] * step
            day_rectangles.append(
                "    "
                f'<rect class="day level-{day["level"]}" '
                f'data-date="{day["date"]}" x="{x}" y="{y}" '
                f'width="{cell}" height="{cell}" rx="2"/>'
            )

    safe_username = escape(username.strip())
    start = dates[0].isoformat()
    end = dates[-1].isoformat()
    return "\n".join(
        [
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
                f'viewBox="0 0 {width} {height}" preserveAspectRatio="xMinYMin meet" '
                'role="img" aria-labelledby="title description" '
                'data-profile-visual="contribution-calendar" '
                'data-calendar-state="generated">'
            ),
            f'  <title id="title">GitHub contribution activity for {safe_username}</title>',
            (
                '  <desc id="description">Contribution activity from '
                f'{start} through {end}, shown as a static calendar heatmap.</desc>'
            ),
            "  <style>",
            "    .background { fill: #f6f8fa; }",
            "    .day { fill: #ebedf0; }",
            "    .level-1 { fill: #9be9a8; }",
            "    .level-2 { fill: #40c463; }",
            "    .level-3 { fill: #30a14e; }",
            "    .level-4 { fill: #216e39; }",
            "    @media (prefers-color-scheme: dark) {",
            "      .background { fill: #0d1117; }",
            "      .day { fill: #161b22; }",
            "      .level-1 { fill: #0e4429; }",
            "      .level-2 { fill: #006d32; }",
            "      .level-3 { fill: #26a641; }",
            "      .level-4 { fill: #39d353; }",
            "    }",
            "  </style>",
            f'  <rect class="background" width="{width}" height="{height}" rx="12"/>',
            '  <g aria-hidden="true">',
            *day_rectangles,
            "  </g>",
            "</svg>",
            "",
        ]
    )


def write_calendar(path: Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(svg)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--endpoint", default=GRAPHQL_ENDPOINT)
    arguments = parser.parse_args()
    token = os.environ.get(arguments.token_env, "")
    try:
        calendar = fetch_contribution_calendar(
            arguments.username,
            token,
            endpoint=arguments.endpoint,
        )
        svg = render_calendar(calendar, arguments.username)
        write_calendar(arguments.output, svg)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        print(f"ERROR: {error}")
        return 1
    print(f"wrote contribution calendar: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
