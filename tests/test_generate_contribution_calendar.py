import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from scripts.generate_contribution_calendar import (
    fetch_contribution_calendar,
    render_calendar,
    write_calendar,
)
from scripts.validate_profile import validate_svg


CALENDAR = {
    "weeks": [
        {
            "contributionDays": [
                {
                    "date": "2026-08-16",
                    "contributionCount": 0,
                    "contributionLevel": "NONE",
                    "weekday": 0,
                },
                {
                    "date": "2026-08-17",
                    "contributionCount": 2,
                    "contributionLevel": "FIRST_QUARTILE",
                    "weekday": 1,
                },
            ]
        },
        {
            "contributionDays": [
                {
                    "date": "2026-08-23",
                    "contributionCount": 7,
                    "contributionLevel": "THIRD_QUARTILE",
                    "weekday": 0,
                },
                {
                    "date": "2026-08-24",
                    "contributionCount": 12,
                    "contributionLevel": "FOURTH_QUARTILE",
                    "weekday": 1,
                },
            ]
        },
    ]
}


class ContributionCalendarTests(unittest.TestCase):
    def test_rendered_svg_is_static_accessible_and_contribution_only(self):
        svg = render_calendar(CALENDAR, "edxi")
        root = ET.fromstring(svg)
        names = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}

        self.assertEqual(root.attrib["role"], "img")
        self.assertEqual(root.attrib["aria-labelledby"], "title description")
        self.assertEqual(root.attrib["data-profile-visual"], "contribution-calendar")
        self.assertEqual(root.attrib["data-calendar-state"], "generated")
        self.assertEqual(root.attrib["width"], "100%")
        self.assertLessEqual(float(root.attrib["viewBox"].split()[2]), 420)
        self.assertLessEqual(float(root.attrib["viewBox"].split()[3]), 260)
        self.assertEqual(names, {"svg", "title", "desc", "style", "g", "rect"})
        self.assertTrue(names.isdisjoint({"text", "path", "circle", "animate"}))

        title = next(element for element in root if element.tag.endswith("title"))
        description = next(element for element in root if element.tag.endswith("desc"))
        self.assertEqual(title.text, "GitHub contribution activity for edxi")
        self.assertIn("2026-08-16 through 2026-08-24", description.text)

        days = [
            (element.attrib["data-date"], element.attrib["class"])
            for element in root.iter()
            if "data-date" in element.attrib
        ]
        self.assertEqual(
            days,
            [
                ("2026-08-16", "day level-0"),
                ("2026-08-17", "day level-1"),
                ("2026-08-23", "day level-3"),
                ("2026-08-24", "day level-4"),
            ],
        )

    def test_fetch_uses_graphql_token_and_returns_calendar(self):
        payload = {
            "data": {
                "user": {
                    "contributionsCollection": {
                        "contributionCalendar": CALENDAR,
                    }
                }
            }
        }
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()

        with mock.patch(
            "scripts.generate_contribution_calendar.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            result = fetch_contribution_calendar(
                "edxi",
                "repository-token",
                endpoint="https://example.test/graphql",
            )

        self.assertEqual(result, CALENDAR)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/graphql")
        self.assertEqual(request.get_header("Authorization"), "Bearer repository-token")
        self.assertEqual(json.loads(request.data)["variables"], {"login": "edxi"})

    def test_malformed_calendar_payload_is_rejected(self):
        cases = (
            {},
            {"weeks": []},
            {"weeks": [{"contributionDays": [{"date": "not-a-date"}]}]},
            {
                "weeks": [
                    {
                        "contributionDays": [
                            {
                                "date": "2026-08-24",
                                "contributionCount": 1,
                                "contributionLevel": "UNKNOWN",
                                "weekday": 1,
                            }
                        ]
                    }
                ]
            },
        )
        for calendar in cases:
            with self.subTest(calendar=calendar):
                with self.assertRaises(ValueError):
                    render_calendar(calendar, "edxi")

    def test_written_calendar_passes_profile_svg_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.svg"
            write_calendar(path, render_calendar(CALENDAR, "edxi"))
            self.assertEqual(validate_svg(path), [])
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))


if __name__ == "__main__":
    unittest.main()
