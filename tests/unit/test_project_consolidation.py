"""Static ownership and application-data decisions for the unified package."""

from __future__ import annotations

import ast
from pathlib import Path

from biocall_studio.studio.application.storage import SuiteDataPaths


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_unified_package_has_strict_workflow_ownership_and_no_removed_namespace():
    """Case: UT-STU-003."""
    root = Path(__file__).resolve().parents[2]
    source = root / "src"
    package = source / "biocall_studio"

    assert not (source / ("biocall_studio" + "_train")).exists()
    assert {path.name for path in package.iterdir() if path.is_dir()} >= {
        "studio",
        "shared",
        "train",
        "detect",
        "review",
        "resources",
    }
    assert {path.name for path in (package / "shared").glob("*.py")} <= {
        "__init__.py",
        "atomic_directory.py",
        "integrity.py",
        "owner_lifetime.py",
        "paths.py",
        "storage.py",
        "worker_launch.py",
    }

    for path in package.rglob("*.py"):
        imports = _imports(path)
        content = path.read_text(encoding="utf-8")
        assert "biocall_studio" + "_train" not in content, path
        relative = path.relative_to(package)
        if relative.parts[0] in {"shared", "train", "detect", "review"}:
            assert not any(name.startswith("biocall_studio.studio") for name in imports), path
        if relative.parts[0] == "train":
            assert not any(name.startswith("biocall_studio.detect") for name in imports), path
        if relative.parts[:2] == ("detect", "domain"):
            assert not any(
                name.startswith(
                    (
                        "PySide6",
                        "biocall_studio.detect.application",
                        "biocall_studio.detect.gui",
                        "biocall_studio.detect.persistence",
                        "biocall_studio.detect.workflows",
                    )
                )
                for name in imports
            ), path
        if relative.parts[:2] == ("review", "domain"):
            assert not any(
                name.startswith(
                    (
                        "PySide6",
                        "biocall_studio.review.application",
                        "biocall_studio.review.gui",
                        "biocall_studio.review.persistence",
                        "biocall_studio.review.workflows",
                    )
                )
                for name in imports
            ), path
        if relative.parts[0] == "shared":
            assert not any(
                name.startswith(
                    (
                        "PySide6",
                        "biocall_studio.train",
                        "biocall_studio.detect",
                        "biocall_studio.review",
                    )
                )
                for name in imports
            ), path


def test_suite_data_paths_are_versioned_separate_and_contained(tmp_path):
    """Case: UT-STU-003."""
    paths = SuiteDataPaths.from_root(tmp_path / "suite-data")

    assert paths.root == (tmp_path / "suite-data").resolve()
    assert paths.train == paths.root / "train" / "v1"
    assert paths.detect == paths.root / "detect" / "v1"
    assert paths.review == paths.root / "review" / "v1"
    assert len({paths.train, paths.detect, paths.review}) == 3
    assert all(
        path.is_relative_to(paths.root) for path in (paths.train, paths.detect, paths.review)
    )
