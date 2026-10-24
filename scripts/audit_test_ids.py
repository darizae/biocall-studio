"""Check indexed test docstrings without importing tests or claiming coverage."""

import ast
import re
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    indexed = set()
    for document in ("UNIT_TESTING.md", "INTEGRATION_TEST_BEHAVIORS.md"):
        prefix = "UT" if document == "UNIT_TESTING.md" else "IT"
        indexed.update(
            re.findall(
                rf"^\| `({prefix}-[A-Z0-9-]+)` \|",
                (root / "docs" / document).read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
    referenced = set()
    unknown = []
    for path in (root / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            case_ids = set(
                re.findall(r"\b(?:UT|IT)-[A-Z0-9]+(?:-[A-Z0-9]+)+", ast.get_docstring(node) or "")
            )
            referenced.update(case_ids)
            for case_id in case_ids - indexed:
                unknown.append(f"{path.relative_to(root)}::{node.name}: unknown ID {case_id}")
    for error in unknown:
        print(error)
    print(f"{len(referenced)} case IDs referenced in test docstrings; {len(unknown)} unknown.")
    print("Static matching does not establish assertions, passing results, or native coverage.")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
