import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


README = Path("README.md")
GITBLOCK = Path("profile-3d-contrib/profile-gitblock.svg")
IMAGE = "![Xi's GitHub contribution activity](./profile-3d-contrib/profile-gitblock.svg)"
LINKS = (
    "[OpenClaw dispatch skills](https://github.com/edxi/openclaw-dispatch-skills)",
    "[VMware ChatOps](https://github.com/edxi/Poshbot.VMware)",
)
HEADINGS = (
    "## Current practice",
    "## Selected work",
    "## Practice areas",
)
BANNED = (
    "## Activity",
    "private repositories",
    "assets/contribution-calendar.svg",
    "github-readme-stats",
    "github-profile-trophy",
    "readme-typing-svg",
    "skill-icons",
)


class ProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = README.read_text(encoding="utf-8")

    def test_readme_has_the_approved_first_screen_order(self):
        self.assertTrue(self.text.startswith("# Hi, I'm Xi\n"))
        self.assertEqual(
            tuple(re.findall(r"^## .+$", self.text, re.MULTILINE)), HEADINGS
        )
        positions = [
            self.text.index("I turn ambiguous ideas"),
            self.text.index(IMAGE),
            *(self.text.index(heading) for heading in HEADINGS),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_readme_has_one_visual_and_two_selected_links(self):
        images = re.findall(r"!\[[^]]*\]\([^)]+\)", self.text)
        links = re.findall(
            r"(?<!!)\[[^]]+\]\((https://github\.com/[^)]+)\)", self.text
        )
        self.assertEqual(images, [IMAGE])
        self.assertEqual(self.text.count(LINKS[0]), 1)
        self.assertEqual(self.text.count(LINKS[1]), 1)
        self.assertEqual(len(links), 2)

    def test_readme_omits_retired_and_decorative_components(self):
        lowered = self.text.lower()
        for token in BANNED:
            self.assertNotIn(token.lower(), lowered)

    def test_gitblock_is_a_real_upstream_svg(self):
        self.assertTrue(GITBLOCK.is_file())
        self.assertGreater(GITBLOCK.stat().st_size, 50_000)
        root = ET.parse(GITBLOCK).getroot()
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")
        self.assertEqual(root.attrib.get("viewBox"), "0 0 1280 850")
        source = GITBLOCK.read_text(encoding="utf-8")
        self.assertIn("contributions", source)
        self.assertIn("<animate", source)
        self.assertGreater(source.count("<rect"), 300)


if __name__ == "__main__":
    unittest.main()
