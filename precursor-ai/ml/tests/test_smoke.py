"""M0 tests: package imports, and the ML track stays isolated from backend wiring."""
import ast
import importlib
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
ROOT = ML_ROOT.parent
sys.path.insert(0, str(ROOT / "ml" / "scripts"))

# ML code may import backend `app.services.*` / `app.core.*` read-only, never these.
FORBIDDEN_PREFIXES = ("app.api", "app.models", "app.db", "app.repositories", "sqlalchemy", "psycopg", "alembic", "fastapi")


def test_package_imports():
    assert importlib.import_module("precursor_ml").__version__


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_ml_does_not_import_api_or_db():
    bad = []
    for py in ML_ROOT.rglob("*.py"):
        if py.name == "test_smoke.py":
            continue
        bad += [f"{py.relative_to(ROOT)}: {n}" for n in _imports(py) if n.startswith(FORBIDDEN_PREFIXES)]
    assert not bad, bad


def test_scope_guard_flags_outside_changes():
    import check_scope as cs

    base = {"backend/a.py": [1, 1], "docs/project/STATUS.md": [1, 1], "gone.py": [1, 1]}
    cur = {"backend/a.py": [2, 2], "docs/project/STATUS.md": [9, 9], "new.py": [1, 1]}
    assert cs.violations(base, cur) == ["added: new.py", "changed: backend/a.py", "removed: gone.py"]
    assert cs.violations(base, base) == []
