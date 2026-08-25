import re
import unittest
from pathlib import Path


WORKFLOW = Path(".github/workflows/update-profile.yml")
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
GITBLOCK = (
    "yoshi389111/github-profile-3d-contrib@"
    "7d95e7d4cdc028dd1e1cbd957d65f35efb12ae39"
)


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_actions_are_exactly_the_reviewed_immutable_pins(self):
        uses = re.findall(r"^\s*uses:\s*(\S+)\s*$", self.text, re.MULTILINE)
        self.assertEqual(uses, [CHECKOUT, CHECKOUT, GITBLOCK])
        for reference in uses:
            self.assertRegex(reference, r"@[0-9a-f]{40}$")

    def test_daily_manual_and_pull_request_triggers_are_present(self):
        self.assertIn("pull_request:", self.text)
        self.assertIn('cron: "17 19 * * *"', self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("update-profile-${{ github.ref }}", self.text)

    def test_permissions_and_generation_inputs_are_minimal(self):
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertEqual(self.text.count("contents: write"), 1)
        self.assertIn("GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", self.text)
        self.assertIn("USERNAME: ${{ github.repository_owner }}", self.text)
        self.assertNotIn("PERSONAL_ACCESS_TOKEN", self.text)
        self.assertNotIn("setup-python", self.text)

    def test_generated_asset_validation_and_commit_are_scoped(self):
        self.assertIn(
            "test -s profile-3d-contrib/profile-gitblock.svg", self.text
        )
        self.assertIn("git add -- profile-3d-contrib/", self.text)
        self.assertIn("git diff --cached --quiet", self.text)
        self.assertNotIn("git add -A", self.text)
        self.assertNotIn("git add .", self.text)
        self.assertNotIn("assets/contribution-calendar.svg", self.text)
        self.assertNotIn("generate_contribution_calendar.py", self.text)
        self.assertNotIn("git add -- README.md", self.text)
        self.assertLess(
            self.text.index("uses: " + GITBLOCK),
            self.text.index("- name: Validate GitBlock output"),
        )
        self.assertLess(
            self.text.index("- name: Validate GitBlock output"),
            self.text.index("- name: Commit generated Profile assets"),
        )


if __name__ == "__main__":
    unittest.main()
