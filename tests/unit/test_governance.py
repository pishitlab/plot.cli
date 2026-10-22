"""Repository checks required by SPEC §16 P1: rule coverage by tests and layering (§4.4)."""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "plot"
TESTS = ROOT / "tests"

RULE_FAMILIES = ("NAME", "DOM", "HOST", "NS")
# Packages services must not depend on: implementations are injected via ports.
FORBIDDEN_FOR_SERVICES = ("plot.api", "plot.cli", "plot.web", "plot.dns", "plot.whois")
# §4.4 allows stdlib + pydantic in core; A-003 adds the approved config readers.
ALLOWED_THIRD_PARTY_FOR_CORE = {"pydantic", "pydantic_settings", "yaml"}


def spec_rule_codes() -> set[str]:
    spec = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
    families = "|".join(RULE_FAMILIES)
    pattern = rf"^\| (R-(?:{families})-\d{{2}}) \|"
    return set(re.findall(pattern, spec, flags=re.MULTILINE))


def rule_codes_in_tests() -> set[str]:
    found: set[str] = set()
    for path in TESTS.rglob("test_*.py"):
        for match in re.finditer(r"def test_(R_[A-Z]+_\d{2})_", path.read_text(encoding="utf-8")):
            found.add(match.group(1).replace("_", "-"))
    return found


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_spec_lists_all_rule_families() -> None:
    codes = spec_rule_codes()
    for family, count in {"NAME": 5, "DOM": 7, "HOST": 7, "NS": 6}.items():
        assert len([c for c in codes if c.startswith(f"R-{family}-")]) == count, family


def test_every_business_rule_has_a_named_test() -> None:
    missing = sorted(spec_rule_codes() - rule_codes_in_tests())
    assert missing == [], f"rules without a test_R_..._ test: {missing}"


def test_services_do_not_import_outer_layers() -> None:
    violations = [
        f"{path.relative_to(ROOT)}: {module}"
        for path in (SRC / "services").rglob("*.py")
        for module in imported_modules(path)
        if module.startswith(FORBIDDEN_FOR_SERVICES)
    ]
    assert violations == []


def test_core_imports_only_stdlib_pydantic_and_config_readers() -> None:
    allowed = set(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY_FOR_CORE
    violations = []
    for path in (SRC / "core").rglob("*.py"):
        for module in imported_modules(path):
            top = module.split(".")[0]
            if (module.startswith("plot.") and not module.startswith("plot.core")) or (
                top != "plot" and top not in allowed
            ):
                violations.append(f"{path.relative_to(ROOT)}: {module}")
    assert violations == []


def test_services_read_time_only_through_clock() -> None:
    banned = re.compile(r"\b(datetime\.now|datetime\.utcnow|date\.today|time\.time|time\.sleep)\(")
    violations = [
        f"{path.relative_to(ROOT)}:{lineno}"
        for path in (SRC / "services").rglob("*.py")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if banned.search(line)
    ]
    assert violations == []
