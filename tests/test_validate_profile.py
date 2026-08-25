import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate_profile import validate_readme, validate_svg


OPENCLAW_LINK = (
    "[OpenClaw dispatch skills]"
    "(https://github.com/edxi/openclaw-dispatch-skills)"
)
VMWARE_LINK = "[VMware ChatOps](https://github.com/edxi/Poshbot.VMware)"
CONTRIBUTION_IMAGE = (
    "![GitHub contribution calendar](assets/contribution-calendar.svg)"
)
VALID_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 384 220" role="img" aria-labelledby="title description" data-profile-visual="contribution-calendar" data-calendar-state="placeholder">
  <title id="title">GitHub contribution activity</title>
  <desc id="description">A static placeholder for the public contribution view.</desc>
  <style>.day { fill: #ebedf0; }</style>
  <g><rect class="day" x="16" y="16" width="10" height="10" rx="2"/></g>
</svg>
"""
SELECTED_WORK_LINES = f"- {OPENCLAW_LINK}\n- {VMWARE_LINK}"

VALID_README = """# Hi, I'm Xi

I turn ambiguous ideas into systems.

## Current practice

Practice.

## Selected work

- [OpenClaw dispatch skills](https://github.com/edxi/openclaw-dispatch-skills)
- [VMware ChatOps](https://github.com/edxi/Poshbot.VMware)

## Activity

![GitHub contribution calendar](assets/contribution-calendar.svg)

## Practice areas

Cloud & Infrastructure
"""


def replace_openclaw(source: str) -> str:
    return VALID_README.replace(OPENCLAW_LINK, source)


def replace_openclaw_with_reference(usage: str, definitions: str) -> str:
    return replace_openclaw(usage).replace(
        "## Selected work",
        f"{definitions}\n\n## Selected work",
    )


def add_to_selected_work(source: str) -> str:
    return VALID_README.replace("## Activity", f"{source}\n\n## Activity")


class ProfileValidationTests(unittest.TestCase):
    def assert_readme_error(self, text: str, phrase: str) -> None:
        errors = validate_readme(text)
        self.assertTrue(any(phrase in item for item in errors), errors)

    def test_valid_profile_passes(self):
        self.assertEqual(validate_readme(VALID_README), [])

    def test_rejects_unapproved_selected_work(self):
        unsafe = VALID_README.replace(
            "https://github.com/edxi/Poshbot.VMware",
            "https://github.com/example/unapproved-repository",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_reordered_duplicate_or_misplaced_canonical_links(self):
        cases = (
            (
                "reordered",
                VALID_README.replace(
                    SELECTED_WORK_LINES,
                    f"- {VMWARE_LINK}\n- {OPENCLAW_LINK}",
                ),
            ),
            (
                "duplicate",
                add_to_selected_work(f"- {OPENCLAW_LINK}"),
            ),
            (
                "outside Selected Work",
                VALID_README.replace(f"- {OPENCLAW_LINK}\n", "")
                + f"\n- {OPENCLAW_LINK}\n",
            ),
        )
        for name, unsafe in cases:
            with self.subTest(name=name):
                self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_canonical_links_inside_inline_code(self):
        unsafe = VALID_README.replace(
            SELECTED_WORK_LINES,
            f"- `{OPENCLAW_LINK}`\n- `{VMWARE_LINK}`",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_canonical_links_inside_fenced_code(self):
        unsafe = VALID_README.replace(
            SELECTED_WORK_LINES,
            f"```markdown\n{SELECTED_WORK_LINES}\n```",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_canonical_links_inside_html_comments(self):
        unsafe = VALID_README.replace(
            SELECTED_WORK_LINES,
            f"<!--\n{SELECTED_WORK_LINES}\n-->",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_canonical_links_in_another_real_section(self):
        unsafe = VALID_README.replace(SELECTED_WORK_LINES, "").replace(
            "Practice.\n",
            f"Practice.\n\n{SELECTED_WORK_LINES}\n",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_fake_heading_substrings_as_section_boundaries(self):
        unsafe = VALID_README.replace(
            f"{SELECTED_WORK_LINES}\n\n",
            "",
        ).replace(
            "Practice.\n\n## Selected work",
            "Practice.\n\n"
            "Fake ## Selected work\n\n"
            f"{SELECTED_WORK_LINES}\n\n"
            "Fake ## Activity\n\n"
            "## Selected work",
        )
        self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_noncanonical_approved_selected_work_link_forms(self):
        cases = (
            (
                "noncanonical label",
                replace_openclaw(
                    "[Dispatch skills]"
                    "(https://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "full reference",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills][dispatch]",
                    "[dispatch]: https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "full reference with angle destination",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills][dispatch]",
                    "[dispatch]: <https://github.com/edxi/openclaw-dispatch-skills>",
                ),
            ),
            (
                "collapsed reference",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills][]",
                    "[OpenClaw dispatch skills]: "
                    "https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "shortcut reference",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills]",
                    "[OpenClaw dispatch skills]: "
                    "https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "duplicate reference definition precedence",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills][dispatch]",
                    "[dispatch]: docs/not-approved.md\n"
                    "[dispatch]: https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "escaped reference label",
                replace_openclaw_with_reference(
                    r"[OpenClaw dispatch skills][dispatch\]]",
                    "[dispatch\\]]: "
                    "https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "multiline reference label",
                replace_openclaw_with_reference(
                    "[OpenClaw dispatch skills][dispatch\n id]",
                    "[dispatch\n id]: "
                    "https://github.com/edxi/openclaw-dispatch-skills",
                ),
            ),
            (
                "angle inline destination",
                replace_openclaw(
                    "[OpenClaw dispatch skills]"
                    "(<https://github.com/edxi/openclaw-dispatch-skills>)"
                ),
            ),
            (
                "multiline inline destination",
                replace_openclaw(
                    "[OpenClaw dispatch skills](\n"
                    "https://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "multiline label",
                replace_openclaw(
                    "[OpenClaw dispatch\n skills]"
                    "(https://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "nested label",
                replace_openclaw(
                    "[OpenClaw [dispatch] skills]"
                    "(https://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "escaped opening bracket",
                replace_openclaw(
                    r"\[OpenClaw dispatch skills]"
                    "(https://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "named entity destination",
                replace_openclaw(
                    "[OpenClaw dispatch skills]"
                    "(https&colon;//github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "decimal entity destination",
                replace_openclaw(
                    "[OpenClaw dispatch skills]"
                    "(https&#58;//github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "hex entity destination",
                replace_openclaw(
                    "[OpenClaw dispatch skills]"
                    "(https&#x3a;//github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "backslash destination",
                replace_openclaw(
                    r"[OpenClaw dispatch skills]"
                    r"(https\://github.com/edxi/openclaw-dispatch-skills)"
                ),
            ),
            (
                "raw HTML anchor",
                replace_openclaw(
                    '<a href="https://github.com/edxi/openclaw-dispatch-skills">'
                    "OpenClaw dispatch skills</a>"
                ),
            ),
            (
                "URI autolink",
                replace_openclaw(
                    "<https://github.com/edxi/openclaw-dispatch-skills>"
                ),
            ),
        )
        for name, unsafe in cases:
            with self.subTest(name=name):
                self.assert_readme_error(unsafe, "selected-work links")

    def test_rejects_extra_selected_work_link_like_constructs(self):
        cases = (
            ("relative inline link", "[Local details](docs/details.md)"),
            ("angle destination", "[Local details](<docs/details.md>)"),
            ("nested label", "[Local [details]](docs/details.md)"),
            ("multiline label", "[Local\n details](docs/details.md)"),
            (
                "full reference",
                "[Local details][local]\n\n[local]: docs/details.md",
            ),
            (
                "collapsed reference",
                "[Local details][]\n\n[Local details]: docs/details.md",
            ),
            (
                "shortcut reference",
                "[Local details]\n\n[Local details]: docs/details.md",
            ),
            ("unused reference definition", "[unused]: docs/details.md"),
            ("escaped opening bracket", r"\[Local details](docs/details.md)"),
            (
                "raw HTML anchor",
                '<a href="docs/details.md">Local details</a>',
            ),
            ("mailto autolink", "<mailto:owner@example.com>"),
            ("email autolink", "<owner@example.com>"),
            ("other URI autolink", "<ftp://example.test/details>"),
        )
        for name, source in cases:
            with self.subTest(name=name):
                self.assert_readme_error(
                    add_to_selected_work(source),
                    "selected-work links",
                )

    def test_rejects_extra_link_like_constructs_outside_selected_work(self):
        cases = (
            ("relative inline link", "[Local details](docs/details.md)"),
            ("unused reference definition", "[unused]: docs/details.md"),
            (
                "full reference",
                "[Local details][local]\n\n[local]: docs/details.md",
            ),
            (
                "raw HTML anchor",
                '<a href="docs/details.md">Local details</a>',
            ),
            ("mailto autolink", "<mailto:owner@example.com>"),
            ("email autolink", "<owner@example.com>"),
            ("uppercase HTTP", "[External](HTTP://example.test)"),
            (
                "named entity HTTP",
                "[External](https&colon;//example.test)",
            ),
            (
                "decimal entity HTTP",
                "[External](https&#58;//example.test)",
            ),
            (
                "hex entity HTTP",
                "[External](https&#x3a;//example.test)",
            ),
            ("backslash HTTP", r"[External](https\://example.test)"),
        )
        for name, source in cases:
            with self.subTest(name=name):
                self.assert_readme_error(
                    f"{VALID_README}\n{source}\n",
                    "README links",
                )

    def test_rejects_out_of_order_or_extra_section(self):
        unsafe = VALID_README.replace(
            "## Activity",
            "## Notes\n\nText\n\n## Activity",
        )
        self.assert_readme_error(unsafe, "section contract")

    def test_rejects_banned_component_or_heading(self):
        cases = (
            (
                "component",
                f"{VALID_README}\ngithub-readme-stats\n",
                "banned component",
            ),
            ("heading", f"{VALID_README}\n## Blog\n", "banned section"),
        )
        for name, unsafe, phrase in cases:
            with self.subTest(name=name):
                self.assert_readme_error(unsafe, phrase)

    def test_rejects_noncanonical_or_additional_image_forms(self):
        replacement_cases = (
            (
                "angle destination",
                "![GitHub contribution calendar]"
                "(<assets/contribution-calendar.svg>)",
            ),
            (
                "multiline alt text",
                "![GitHub contribution\n calendar]"
                "(assets/contribution-calendar.svg)",
            ),
            (
                "nested alt text",
                "![GitHub [contribution] calendar]"
                "(assets/contribution-calendar.svg)",
            ),
            (
                "escaped opening marker",
                r"\![GitHub contribution calendar]"
                "(assets/contribution-calendar.svg)",
            ),
            (
                "entity brackets",
                "!&#91;GitHub contribution calendar&#93;"
                "(assets/contribution-calendar.svg)",
            ),
            (
                "full reference",
                "![GitHub contribution calendar][calendar]\n\n"
                "[calendar]: assets/contribution-calendar.svg",
            ),
            (
                "collapsed reference",
                "![GitHub contribution calendar][]\n\n"
                "[GitHub contribution calendar]: assets/contribution-calendar.svg",
            ),
            (
                "shortcut reference",
                "![GitHub contribution calendar]\n\n"
                "[GitHub contribution calendar]: assets/contribution-calendar.svg",
            ),
            (
                "raw HTML image",
                '<img alt="GitHub contribution calendar" '
                'src="assets/contribution-calendar.svg">',
            ),
        )
        additional_cases = (
            ("duplicate canonical image", CONTRIBUTION_IMAGE),
            ("second inline image", "![Extra](assets/extra.svg)"),
            (
                "multiline full reference image",
                "![Extra\n image][extra]\n\n[extra]: assets/extra.svg",
            ),
            (
                "multiline collapsed reference image",
                "![Extra\n image][]\n\n[Extra image]: assets/extra.svg",
            ),
            (
                "multiline shortcut reference image",
                "![Extra\n image]\n\n[Extra image]: assets/extra.svg",
            ),
            (
                "raw HTML image",
                '<img alt="Extra" src="assets/extra.svg">',
            ),
        )
        for name, source in replacement_cases:
            with self.subTest(kind="replacement", name=name):
                unsafe = VALID_README.replace(CONTRIBUTION_IMAGE, source)
                self.assert_readme_error(unsafe, "exactly one local image")
        for name, source in additional_cases:
            with self.subTest(kind="additional", name=name):
                unsafe = VALID_README.replace(
                    "## Practice areas",
                    f"{source}\n\n## Practice areas",
                )
                self.assert_readme_error(unsafe, "exactly one local image")

    def test_rejects_canonical_image_inside_inline_code(self):
        unsafe = VALID_README.replace(
            CONTRIBUTION_IMAGE,
            f"`{CONTRIBUTION_IMAGE}`",
        )
        self.assert_readme_error(unsafe, "exactly one local image")

    def test_rejects_canonical_image_inside_fenced_code(self):
        unsafe = VALID_README.replace(
            CONTRIBUTION_IMAGE,
            f"```markdown\n{CONTRIBUTION_IMAGE}\n```",
        )
        self.assert_readme_error(unsafe, "exactly one local image")

    def test_rejects_canonical_image_inside_html_comments(self):
        unsafe = VALID_README.replace(
            CONTRIBUTION_IMAGE,
            f"<!-- {CONTRIBUTION_IMAGE} -->",
        )
        self.assert_readme_error(unsafe, "exactly one local image")

    def test_rejects_canonical_image_in_another_real_section(self):
        unsafe = VALID_README.replace(
            f"\n{CONTRIBUTION_IMAGE}\n",
            "\n",
        ).replace(
            "Practice.\n",
            f"Practice.\n\n{CONTRIBUTION_IMAGE}\n",
        )
        self.assert_readme_error(unsafe, "exactly one local image")

    def test_svg_requires_a_complete_svg_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.svg"
            path.write_text("not svg", encoding="utf-8")
            self.assertTrue(validate_svg(path))
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                encoding="utf-8",
            )
            self.assertTrue(validate_svg(path))
            path.write_text(VALID_SVG, encoding="utf-8")
            self.assertEqual(validate_svg(path), [])

    def test_svg_rejects_dashboard_animation_or_missing_accessibility(self):
        mutations = (
            VALID_SVG.replace(' role="img"', ""),
            VALID_SVG.replace(' aria-labelledby="title description"', ""),
            VALID_SVG.replace(' data-profile-visual="contribution-calendar"', ""),
            VALID_SVG.replace("</g>", "<animate attributeName=\"x\"/></g>"),
            VALID_SVG.replace("</g>", "<text>Commit</text></g>"),
            VALID_SVG.replace("</g>", "<path d=\"M0 0\"/></g>"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.svg"
            for source in mutations:
                with self.subTest(source=source):
                    path.write_text(source, encoding="utf-8")
                    self.assertTrue(validate_svg(path))

    def test_cli_reports_missing_readme_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_readme = root / "missing.md"
            svg = root / "calendar.svg"
            svg.write_text(VALID_SVG, encoding="utf-8")
            script = Path(__file__).parents[1] / "scripts" / "validate_profile.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--readme",
                    str(missing_readme),
                    "--svg",
                    str(svg),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("ERROR: README cannot be read:", completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_cli_reports_unreadable_svg_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            svg = root / "calendar.svg"
            readme.write_text(VALID_README, encoding="utf-8")
            svg.write_text(VALID_SVG, encoding="utf-8")
            script = Path(__file__).parents[1] / "scripts" / "validate_profile.py"
            svg.chmod(0)
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--readme",
                        str(readme),
                        "--svg",
                        str(svg),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                svg.chmod(stat.S_IRUSR | stat.S_IWUSR)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("ERROR: SVG cannot be read:", completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertNotIn("Traceback", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
