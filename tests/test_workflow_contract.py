import re
import unittest
from pathlib import Path


WORKFLOW = Path(".github/workflows/update-profile.yml")
APPROVED_USES = (
    "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405",
)
EXPECTED_PERMISSIONS = {
    "global": {"contents": "read"},
    "validate-profile": {"contents": "read"},
    "update-profile": {"contents": "write"},
}
EXPECTED_UPDATE_CONDITION = (
    "if: github.event_name != 'pull_request' && github.ref_type == 'branch'"
)
EXPECTED_UPDATE_CONDITION_VALUE = EXPECTED_UPDATE_CONDITION.split(":", 1)[1].strip()
APPROVED_COMMIT_BLOCK = """          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -- assets/contribution-calendar.svg
          if git diff --cached --quiet; then
            echo "Contribution calendar is unchanged."
            exit 0
          fi
          git commit -m "chore: refresh profile activity"
          git pull --rebase origin "${GITHUB_REF_NAME}"
          git push origin "HEAD:${GITHUB_REF_NAME}"
"""
APPROVED_GENERATOR_STEP = """      - name: Generate contribution calendar
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_USERNAME: ${{ github.repository_owner }}
        run: |
          set -euo pipefail
          python scripts/generate_contribution_calendar.py \\
            --username "$GITHUB_USERNAME" \\
            --output assets/contribution-calendar.svg

"""
def uncomment(line: str) -> str:
    quote = ""
    index = 0
    while index < len(line):
        character = line[index]
        if quote == "'" and character == "'":
            if index + 1 < len(line) and line[index + 1] == "'":
                index += 2
                continue
            quote = ""
        elif quote == '"' and character == '"':
            quote = ""
        elif not quote and character in "'\"":
            quote = character
        elif not quote and character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
        index += 1
    return line


def mapping_yaml_lines(text: str) -> list[tuple[int, int, str]]:
    active: list[tuple[int, int, str]] = []
    scalar_indent: int | None = None
    for index, raw in enumerate(text.splitlines()):
        indent = len(raw) - len(raw.lstrip())
        if scalar_indent is not None:
            if not raw.strip() or indent > scalar_indent:
                continue
            scalar_indent = None
        line = uncomment(raw)
        if not line.strip():
            continue
        active.append((index, indent, line))
        if re.search(r":\s*[>|][+-]?\d?\s*$", line):
            scalar_indent = indent
    return active


def expression_yaml_lines(text: str) -> list[str]:
    active: list[str] = []
    scalar_indent: int | None = None
    for raw in text.splitlines():
        indent = len(raw) - len(raw.lstrip())
        if scalar_indent is not None:
            if not raw.strip():
                continue
            if indent > scalar_indent:
                active.append(raw)
                continue
            scalar_indent = None
        line = uncomment(raw)
        if not line.strip():
            continue
        active.append(line)
        if re.search(r":\s*[>|][+-]?\d?\s*$", line):
            scalar_indent = indent
    return active


def block_mapping(line: str) -> tuple[str, str] | None:
    line = re.sub(r"^(\s*)-\s+", r"\1", line, count=1)
    match = re.match(
        r"^\s*(?:(['\"])(.*?)\1|([^:#][^:]*?))\s*:\s*(.*)$",
        line,
    )
    if not match:
        return None
    key = (match.group(2) if match.group(1) else match.group(3)).strip()
    return key, match.group(4).strip()


def flow_mappings(line: str) -> list[tuple[str, str]]:
    stripped = line.lstrip()
    block = block_mapping(line)
    if not (
        stripped.startswith("- {")
        or block is not None and block[1].startswith("{")
    ):
        return []
    mappings: list[tuple[str, str]] = []
    for match in re.finditer(
        r"(?:\{|,)\s*(?:(['\"])(.*?)\1|([^,:{}][^:]*?))\s*:\s*([^,}]*)",
        line,
    ):
        key = (match.group(2) if match.group(1) else match.group(3)).strip()
        mappings.append((key, match.group(4).strip()))
    return mappings


def mapping_entries(text: str) -> list[tuple[int, int, str, str, bool]]:
    entries: list[tuple[int, int, str, str, bool]] = []
    for index, indent, line in mapping_yaml_lines(text):
        block = block_mapping(line)
        if block is not None:
            entries.append((index, indent, *block, False))
        entries.extend((index, indent, key, value, True) for key, value in flow_mappings(line))
    return entries


def permission_mappings(text: str) -> dict[str, dict[str, str]]:
    lines = mapping_yaml_lines(text)
    result: dict[str, dict[str, str]] = {}
    current_job = ""
    for position, (index, indent, line) in enumerate(lines):
        mapping = block_mapping(line)
        if mapping is None:
            continue
        key, value = mapping
        if indent == 2:
            current_job = key
        if key != "permissions":
            continue
        scope = "global" if indent == 0 else current_job if indent == 4 else ""
        inline_value = value
        if not scope or scope in result or inline_value and not inline_value.startswith("#"):
            result[f"invalid:{index}"] = {}
            continue
        mapping: dict[str, str] = {}
        for _, child_indent, child in lines[position + 1 :]:
            if child_indent <= indent:
                break
            child_mapping = block_mapping(child)
            if child_indent != indent + 2 or child_mapping is None:
                mapping[f"invalid:{child.strip()}"] = ""
                continue
            child_key, child_value = child_mapping
            mapping[child_key] = child_value
        result[scope] = mapping
    return result


def calendar_errors(text: str) -> list[str]:
    blocks = re.findall(
        r"(?ms)^      - name: Commit real calendar changes\n        run: \|\n"
        r"((?:          .*\n)*)",
        text,
    )
    if blocks != [APPROVED_COMMIT_BLOCK]:
        return ["calendar mutation block must be canonical"]
    return []


def generator_errors(text: str) -> list[str]:
    blocks = re.findall(
        r"(?ms)^      - name: Generate contribution calendar\n"
        r".*?(?=^      - name: |\Z)",
        text,
    )
    if blocks != [APPROVED_GENERATOR_STEP]:
        return ["calendar generator step must be canonical"]
    return []


def update_job_conditions(text: str) -> list[str]:
    lines = mapping_yaml_lines(text)
    headers = [
        (position, index)
        for position, (index, indent, key, value, flow) in enumerate(mapping_entries(text))
        if key == "update-profile" and indent == 2 and not flow and not value
    ]
    if len(headers) != 1:
        return []
    _, header_index = headers[0]
    conditions: list[str] = []
    in_update_job = False
    for index, indent, line in lines:
        if index == header_index:
            in_update_job = True
            continue
        if in_update_job and indent <= 2:
            break
        mapping = block_mapping(line)
        if in_update_job and indent == 4 and mapping is not None and mapping[0] == "if":
            conditions.append(mapping[1])
    return conditions


def github_expressions(text: str) -> list[str]:
    source = "\n".join(expression_yaml_lines(text))
    return [expression.strip() for expression in re.findall(r"\$\{\{(.*?)\}\}", source)]


def generator_token_lines(text: str) -> list[str]:
    token_lines: list[str] = []
    in_generator = False
    in_env = False
    for _, indent, line in mapping_yaml_lines(text):
        stripped = line.strip()
        if indent == 6 and stripped == "- name: Generate contribution calendar":
            in_generator = True
            in_env = False
            continue
        if in_generator and indent == 6 and stripped.startswith("- "):
            break
        if in_generator and indent == 8 and stripped == "env:":
            in_env = True
            continue
        if in_env and indent <= 8:
            in_env = False
        mapping = block_mapping(line)
        if in_env and indent == 10 and mapping is not None and mapping[0] == "GITHUB_TOKEN":
            token_lines.append(stripped)
    return token_lines


def workflow_errors(text: str) -> list[str]:
    errors: list[str] = []
    entries = mapping_entries(text)
    uses = tuple(value for _, _, key, value, _ in entries if key == "uses")
    if uses != APPROVED_USES:
        errors.append("uses references must equal the reviewed allowlist")
    permissions = [entry for entry in entries if entry[2] == "permissions"]
    if len(permissions) != 3 or permission_mappings(text) != EXPECTED_PERMISSIONS:
        errors.append("permission mappings must be exact")
    credential_expressions = [
        expression
        for expression in github_expressions(text)
        if re.search(r"\bsecrets\b|\bgithub\s*(?:\[|\.\s*token\b)", expression)
    ]
    if (
        credential_expressions != ["secrets.GITHUB_TOKEN"]
        or generator_token_lines(text) != ["GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}"]
    ):
        errors.append("secret references must contain only the repository token")
    errors.extend(calendar_errors(text))
    errors.extend(generator_errors(text))
    update_headers = [entry for entry in entries if entry[2] == "update-profile"]
    if (
        len(update_headers) != 1
        or update_job_conditions(text) != [EXPECTED_UPDATE_CONDITION_VALUE]
    ):
        errors.append("update job must require a non-pull-request branch ref")
    return errors


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_approved_workflow_has_no_contract_errors(self):
        self.assertEqual(workflow_errors(self.text), [])
        harmless_comments = self.text.replace(
            "permissions:\n  contents: read",
            "permissions:\n  contents: read\n"
            "# permissions: are intentionally minimal\n"
            "# secrets are unavailable to pull requests",
            1,
        )
        self.assertEqual(workflow_errors(harmless_comments), [])
        scalar_prose = self.text.replace(
            "      - name: Run contract tests",
            "      - name: Contract note\n"
            "        run: |\n"
            '          echo "permissions: prose only"\n'
            '          echo "secrets are unavailable here"\n\n'
            "      - name: Run contract tests",
        )
        self.assertEqual(workflow_errors(scalar_prose), [])

    def test_schedule_dispatch_nonce_and_concurrency_are_present(self):
        self.assertIn('cron: "19 18 * * 0"', self.text)
        self.assertIn("correlation_id:", self.text)
        self.assertIn("required: true", self.text)
        self.assertIn(
            "run-name: Update profile / ${{ inputs.correlation_id || 'scheduled' }}",
            self.text,
        )
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn(EXPECTED_UPDATE_CONDITION, self.text)
        unsafe = self.text.replace(
            EXPECTED_UPDATE_CONDITION,
            "if: github.event_name != 'pull_request'",
        )
        self.assertIn("branch ref", " ".join(workflow_errors(unsafe)))
        duplicate = self.text.replace(
            EXPECTED_UPDATE_CONDITION,
            EXPECTED_UPDATE_CONDITION
            + "\n    if: github.event_name != 'pull_request'",
        )
        self.assertIn("branch ref", " ".join(workflow_errors(duplicate)))
        quoted_duplicate = self.text.replace(
            EXPECTED_UPDATE_CONDITION,
            EXPECTED_UPDATE_CONDITION
            + "\n    'if': github.event_name != 'pull_request'",
        )
        self.assertIn("branch ref", " ".join(workflow_errors(quoted_duplicate)))
        prefix, _ = self.text.split("  update-profile:\n", 1)
        flow = prefix + (
            "  update-profile: {if: github.event_name != 'pull_request' && "
            "github.ref_type == 'branch', permissions: {contents: write}, "
            "runs-on: ubuntu-24.04, steps: []}\n"
        )
        self.assertIn("branch ref", " ".join(workflow_errors(flow)))

    def test_calendar_only_staging_and_idempotency_are_present(self):
        self.assertIn("git add -- assets/contribution-calendar.svg", self.text)
        self.assertNotIn("git add -- README.md", self.text)
        self.assertIn("git diff --cached --quiet", self.text)
        self.assertIn("scripts/generate_contribution_calendar.py", self.text)
        self.assertNotIn("profile-night-green.svg", self.text)
        self.assertNotIn("github-profile-3d-contrib", self.text)
        unsafe_generator = self.text.replace(
            "python scripts/generate_contribution_calendar.py",
            "python scripts/unreviewed_generator.py",
        )
        self.assertIn("generator", " ".join(workflow_errors(unsafe_generator)))
        mutations = {
            "add all": "git add -A",
            "add dot": "git add .",
            "add other path": "git add -- README.md",
            "add multiple paths": "git add -- assets/contribution-calendar.svg README.md",
            "commit all": 'git commit -a -m "chore: refresh profile activity"',
            "update index": "git update-index --add README.md",
            "prefixed add": "env git add -- README.md",
            "subshell add": "$(git add -- README.md)",
        }
        for name, command in mutations.items():
            with self.subTest(name=name):
                unsafe = self.text.replace(
                    'git commit -m "chore: refresh profile activity"',
                    'git commit -m "chore: refresh profile activity"\n'
                    f"          {command}",
                )
                self.assertIn("calendar", " ".join(workflow_errors(unsafe)))

    def test_rejects_additional_action_reference(self):
        mutations = {
            "block": (
                "      - name: Run contract tests",
                "      - name: Unreviewed action\n"
                "        uses: owner/unreviewed@0123456789abcdef\n\n"
                "      - name: Run contract tests",
            ),
            "flow": (
                "      - name: Run contract tests",
                "      - {name: Unreviewed action, "
                "uses: owner/unreviewed@0123456789abcdef}\n\n"
                "      - name: Run contract tests",
            ),
            "compact unquoted": (
                "      - name: Run contract tests",
                "      - uses: owner/unreviewed@0123456789abcdef\n\n"
                "      - name: Run contract tests",
            ),
            "compact single quoted": (
                "      - name: Run contract tests",
                "      - 'uses': owner/unreviewed@0123456789abcdef\n\n"
                "      - name: Run contract tests",
            ),
            "compact double quoted": (
                "      - name: Run contract tests",
                '      - "uses": owner/unreviewed@0123456789abcdef\n\n'
                "      - name: Run contract tests",
            ),
        }
        for name, (before, after) in mutations.items():
            with self.subTest(name=name):
                unsafe = self.text.replace(before, after)
                self.assertIn("uses references", " ".join(workflow_errors(unsafe)))

    def test_rejects_additional_write_permission(self):
        injected_job = (
            "  injected:\n"
            "    permissions: {permission}\n"
            "    runs-on: ubuntu-24.04\n"
            "    steps: []\n\n"
            "  update-profile:"
        )
        mutations = {
            "additional mapping key": self.text.replace(
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  actions: write",
                1,
            ),
            "scalar": self.text.replace(
                "  update-profile:",
                injected_job.format(permission="write-all"),
            ),
            "flow mapping": self.text.replace(
                "  update-profile:",
                injected_job.format(permission="{actions: write}"),
            ),
            "additional job": self.text.replace(
                "  update-profile:",
                injected_job.format(permission="contents: read"),
            ),
            "flow style added job": self.text.replace(
                "  update-profile:",
                "  injected: {permissions: write-all, runs-on: ubuntu-24.04, "
                "steps: []}\n\n  update-profile:",
            ),
            "duplicate block": self.text.replace(
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\npermissions:\n  contents: read",
                1,
            ),
        }
        for name, unsafe in mutations.items():
            with self.subTest(name=name):
                self.assertIn("permission mappings", " ".join(workflow_errors(unsafe)))

    def test_rejects_unapproved_secret_reference(self):
        expressions = {
            "dot secret": "secrets.EXTRA_TOKEN",
            "single quoted secret index": "secrets['EXTRA_TOKEN']",
            "double quoted secret index": 'secrets["EXTRA_TOKEN"]',
            "github token index": "github['token']",
            "computed secret index": "secrets[format('EXTRA_{0}', 'TOKEN')]",
        }
        for name, expression in expressions.items():
            with self.subTest(name=name):
                unsafe = self.text.replace(
                    "GITHUB_USERNAME: ${{ github.repository_owner }}",
                    "GITHUB_USERNAME: ${{ github.repository_owner }}\n"
                    f"          EXTRA_TOKEN: ${{{{ {expression} }}}}",
                )
                self.assertIn("secret references", " ".join(workflow_errors(unsafe)))
        block_scalar_expressions = {
            "literal block scalar secret": "secrets.EXTRA_TOKEN",
            "computed block scalar secret": "secrets[format('EXTRA_{0}', 'TOKEN')]",
        }
        for name, expression in block_scalar_expressions.items():
            with self.subTest(name=name):
                unsafe = self.text.replace(
                    "        run: python -m unittest discover -s tests -v",
                    "        run: |\n"
                    f'          echo "${{{{ {expression} }}}}"\n'
                    "          python -m unittest discover -s tests -v",
                )
                self.assertIn("secret references", " ".join(workflow_errors(unsafe)))


if __name__ == "__main__":
    unittest.main()
