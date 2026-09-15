import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rewrite_language_pie as pie  # noqa: E402

GITBLOCK = ROOT / "profile-3d-contrib" / "profile-gitblock.svg"


ROWS = (
    {
        "repository": {
            "name": "edxi.github.io",
            "primaryLanguage": None,
        },
        "contributions": {"totalCount": 7},
    },
    {
        "repository": {
            "name": "ob",
            "primaryLanguage": None,
        },
        "contributions": {"totalCount": 2},
    },
    {
        "repository": {
            "name": "xijia-agent-skills",
            "primaryLanguage": {"name": "Python", "color": "#3572A5"},
        },
        "contributions": {"totalCount": 3},
    },
    {
        "repository": {
            "name": "crawler",
            "primaryLanguage": {"name": "Go", "color": "#00ADD8"},
        },
        "contributions": {"totalCount": 1},
    },
    {
        "repository": {
            "name": "Poshbot.VMware",
            "primaryLanguage": {"name": "PowerShell", "color": "#012456"},
        },
        "contributions": {"totalCount": 1},
    },
    {
        "repository": {
            "name": "openclaw-dispatch-skills",
            "primaryLanguage": {"name": "Shell", "color": "#89e051"},
        },
        "contributions": {"totalCount": 1},
    },
    {
        "repository": {
            "name": "legacy-site",
            "primaryLanguage": {"name": "HTML", "color": "#e34c26"},
        },
        "contributions": {"totalCount": 40},
    },
    {
        "repository": {
            "name": "xijia-aws-foundation",
            "primaryLanguage": {"name": "HCL", "color": "#844FBA"},
        },
        "contributions": {"totalCount": 1},
    },
)


UPSTREAM_PATHS = {
    "Python 3": (
        "M0,-117A117,117,0,0,1,111.274,-36.155L61.819,-20.086A65,65,0,0,0,0,-65Z"
    ),
    "Go 1": (
        "M111.274,-36.155A117,117,0,0,1,116.359,12.23L64.644,6.794"
        "A65,65,0,0,0,61.819,-20.086Z"
    ),
    "PowerShell 1": (
        "M116.359,12.23A117,117,0,0,1,101.325,58.5L56.292,32.5"
        "A65,65,0,0,0,64.644,6.794Z"
    ),
    "Shell 1": (
        "M101.325,58.5A117,117,0,0,1,68.771,94.655L38.206,52.586"
        "A65,65,0,0,0,56.292,32.5Z"
    ),
    "other 9": (
        "M68.771,94.655A117,117,0,1,1,0,-117L0,-65A65,65,0,1,0,38.206,52.586Z"
    ),
}


class LanguagePieTests(unittest.TestCase):
    def test_languageless_and_html_commits_are_omitted_not_folded_into_other(self):
        languages = pie.aggregate_languages(
            ROWS,
            exclude_repos=("edxi.github.io", "ob"),
            exclude_languages=("HTML",),
        )
        names = [item.language for item in languages]
        self.assertEqual(names, ["Python", "Go", "HCL", "PowerShell", "Shell"])
        slices = pie.pie_slices(languages)
        self.assertEqual(
            [(item.language, item.contributions) for item in slices],
            [
                ("Python", 3),
                ("Go", 1),
                ("HCL", 1),
                ("PowerShell", 1),
                ("Shell", 1),
            ],
        )
        self.assertNotIn("other", [item.language for item in slices])

    def test_other_is_the_tail_of_classified_languages_only(self):
        languages = [
            pie.Slice("Python", "#3572A5", 10),
            pie.Slice("Go", "#00ADD8", 8),
            pie.Slice("HCL", "#844FBA", 6),
            pie.Slice("TypeScript", "#3178c6", 5),
            pie.Slice("Shell", "#89e051", 4),
            pie.Slice("Lua", "#000080", 2),
            pie.Slice("PowerShell", "#012456", 1),
        ]
        slices = pie.pie_slices(languages)
        self.assertEqual(
            [(item.language, item.contributions) for item in slices],
            [
                ("Python", 10),
                ("Go", 8),
                ("HCL", 6),
                ("TypeScript", 5),
                ("Shell", 4),
                ("other", 3),
            ],
        )

    def test_donut_paths_match_upstream_d3_output(self):
        slices = [
            pie.Slice("Python", "#3572A5", 3),
            pie.Slice("Go", "#00ADD8", 1),
            pie.Slice("PowerShell", "#012456", 1),
            pie.Slice("Shell", "#89e051", 1),
            pie.Slice("other", "#444444", 9),
        ]
        markup = pie.render_pie_group(slices, animated=False)
        for title, path in UPSTREAM_PATHS.items():
            self.assertIn(f'd="{path}"', markup)
            self.assertIn(f"<title>{title}</title>", markup)

    def test_existing_svg_fallback_drops_other(self):
        svg = GITBLOCK.read_text(encoding="utf-8")
        slices = pie.slices_from_existing_svg(svg)
        self.assertEqual(
            [(item.language, item.contributions) for item in slices],
            [
                ("Python", 3),
                ("Go", 1),
                ("PowerShell", 1),
                ("Shell", 1),
            ],
        )

    def test_replace_pie_group_preserves_the_rest_of_the_svg(self):
        svg = GITBLOCK.read_text(encoding="utf-8")
        slices = pie.pie_slices(pie.slices_from_existing_svg(svg))
        rewritten = pie.replace_pie_group(
            svg, pie.render_pie_group(slices, pie.pie_is_animated(svg))
        )
        self.assertIn("<title>Python 3</title>", rewritten)
        self.assertNotIn("<title>other 9</title>", rewritten)
        self.assertNotIn(">other<", rewritten)
        self.assertIn("contributions", rewritten)
        self.assertTrue(rewritten.startswith("<svg "))
        self.assertTrue(rewritten.rstrip().endswith("</svg>"))
        self.assertGreater(rewritten.count("<rect"), 300)


if __name__ == "__main__":
    unittest.main()
