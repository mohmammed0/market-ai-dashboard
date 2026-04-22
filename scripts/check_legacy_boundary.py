from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODERN_DIRS = [
    ROOT / "backend",
    ROOT / "core",
    ROOT / "scripts",
]

ALLOWED_LEGACY_PATHS = {
    ROOT / "core" / "legacy_adapters",
}


class LegacyImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name.startswith("legacy"):
                self.violations.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module.startswith("legacy"):
            self.violations.append(module)
        self.generic_visit(node)


def _is_allowed_path(path: Path) -> bool:
    for allowed in ALLOWED_LEGACY_PATHS:
        if allowed in path.parents:
            return True
    return False


def _scan_file(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    visitor = LegacyImportVisitor()
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    violations: list[str] = []
    for base in MODERN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_allowed_path(path):
                continue
            file_violations = _scan_file(path)
            if file_violations:
                for module in file_violations:
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
    if violations:
        print("Forbidden legacy imports detected:")
        for item in sorted(violations):
            print(f" - {item}")
        return 1
    print("Legacy import boundary check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
