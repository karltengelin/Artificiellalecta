"""Deklarativt, konservativt testurval med redovisade beroenden."""

from __future__ import annotations

import ast
import fnmatch
import subprocess
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CATALOG = "tests/suites.toml"


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    status: str
    tests: tuple[str, ...]
    dependents: tuple[str, ...]


@dataclass(frozen=True)
class Rule:
    paths: tuple[str, ...]
    suites: tuple[str, ...]
    full: bool
    documentation: bool
    postgres: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    suites: dict[str, Suite]
    markers: dict[str, tuple[str, ...]]
    rules: tuple[Rule, ...]

    @property
    def tests(self) -> tuple[str, ...]:
        return tuple(sorted({path for suite in self.suites.values() for path in suite.tests}))


@dataclass(frozen=True)
class Plan:
    suites: tuple[str, ...]
    tests: tuple[str, ...]
    reasons: tuple[str, ...]
    full: bool = False
    postgres: tuple[str, ...] = ()  # Postgres-prov som ändringen berör; körs bara med --postgres


def relative_path(value: str) -> str:
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ":" in value or ".." in path.parts:
        raise SelectionError(f"Förväntade en sökväg relativt reporoten: {value!r}")
    return path.as_posix()


def load_catalog(root: Path = ROOT) -> Catalog:
    try:
        raw = tomllib.loads((root / CATALOG).read_text(encoding="utf-8"))
        if raw.get("version") != 1 or set(raw) != {"version", "suites", "markers", "rules"}:
            raise SelectionError("Okänd version eller okända fält i testkatalogen")
        suites = {}
        for name, row in raw["suites"].items():
            if not name.isidentifier() or set(row) != {"description", "status", "tests", "dependents"}:
                raise SelectionError(f"Ogiltig testgrupp: {name}")
            suites[name] = Suite(name, row["description"], row["status"],
                                 tuple(row["tests"]), tuple(row["dependents"]))
        markers = {name: tuple(paths) for name, paths in raw["markers"].items()}
        rules = []
        for row in raw["rules"]:
            if set(row) - {"paths", "suites", "full", "documentation", "postgres"}:
                raise SelectionError("Okänt fält i ändringsregel")
            rules.append(Rule(tuple(row["paths"]), tuple(row.get("suites", ())),
                              row.get("full", False), row.get("documentation", False),
                              tuple(row.get("postgres", ()))))
        catalog = Catalog(suites, markers, tuple(rules))
        validate_catalog(catalog, root)
        return catalog
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise SelectionError(f"Testkatalogen kunde inte läsas: {exc}") from exc


def validate_catalog(catalog: Catalog, root: Path) -> None:
    for name, suite in catalog.suites.items():
        if suite.status not in {"active", "partial", "planned"}:
            raise SelectionError(f"Okänd status för {name}")
        if bool(suite.tests) == (suite.status == "planned"):
            raise SelectionError(f"{name}: planned ska vara tom; active/partial ska ha tester")
        if len(suite.tests) != len(set(suite.tests)):
            raise SelectionError(f"Dubbla testfiler i {name}")
        for dependent in suite.dependents:
            if dependent not in catalog.suites:
                raise SelectionError(f"Okänd beroendegrupp: {dependent}")
        for path in suite.tests:
            if relative_path(path) != path or not path.startswith("tests/") or not (root / path).is_file():
                raise SelectionError(f"Saknad eller ogiltig testfil: {path}")
    discovered = {
        p.relative_to(root).as_posix() for p in (root / "tests").rglob("*.py")
        if p.name.startswith("test_") or p.name.endswith("_test.py")
    }
    if discovered != set(catalog.tests):
        raise SelectionError(f"Uppdatera {CATALOG}; omappade tester: {sorted(discovered - set(catalog.tests))}; "
                             f"inte testfiler: {sorted(set(catalog.tests) - discovered)}")
    for name, selectors in catalog.markers.items():
        if name not in {"postgres", "integration", "security"}:
            raise SelectionError(f"Okänd testegenskap: {name}")
        for selector in selectors:
            file, *nodes = selector.split("::")
            if file not in catalog.tests:
                raise SelectionError(f"Testegenskap pekar på okänd testfil: {selector}")
            # Kontrollera också funktions-/klassnamn; ett namnbyte får inte tappa Postgres-markeringen.
            scope = ast.parse((root / file).read_text(encoding="utf-8")).body
            for node in nodes:
                found = next((n for n in scope if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                              and n.name == node), None)
                if found is None:
                    raise SelectionError(f"Testegenskap pekar på okänt test: {selector}")
                scope = found.body
    postgres = catalog.markers.get("postgres", ())
    for rule in catalog.rules:
        kinds = sum((bool(rule.suites), rule.full, rule.documentation))
        if not rule.paths or kinds != (0 if rule.postgres else 1):
            raise SelectionError("Varje ändringsregel ska välja grupper, hela sviten, dokumentation "
                                 "eller enbart Postgres-prov")
        for selector in rule.postgres:
            if not any(marker_matches(selector, marked) for marked in postgres):
                raise SelectionError(f"Postgres-regel pekar på prov utan markören postgres: {selector}")
        for pattern in rule.paths:
            relative_path(pattern)
        if any(name not in catalog.suites for name in rule.suites):
            raise SelectionError("Ändringsregel pekar på okänd testgrupp")
    # Några testmoduler används också som gemensamma hjälpare. De kan inte väljas isolerat.
    for path in catalog.tests:
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
        # En fil som skapar scheman i testdatabasen ska ha markören, annars körs den utan aktivt val.
        names = {getattr(node, "id", None) or getattr(node, "name", None) for node in ast.walk(tree)
                 if isinstance(node, (ast.Name, ast.alias, ast.FunctionDef))}
        if "isolated_schema" in names and not any(marked.split("::")[0] == path for marked in postgres):
            raise SelectionError(f"{path} använder isolated_schema men saknar markören postgres")
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        for module in imports:
            helper = module.replace(".", "/") + ".py"
            if helper in catalog.tests and not any(
                rule.full and any(fnmatch.fnmatchcase(helper, pattern) for pattern in rule.paths)
                for rule in catalog.rules
            ):
                raise SelectionError(f"Delad testhjälpare {helper}: lägg till en regel för hela sviten")


def expand_suites(catalog: Catalog, names: set[str]) -> tuple[str, ...]:
    pending = list(names)
    expanded: set[str] = set()
    while pending:
        name = pending.pop()
        if name not in catalog.suites:
            raise SelectionError(f"Okänd testgrupp: {name}")
        if name not in expanded:
            expanded.add(name)
            pending.extend(catalog.suites[name].dependents)
    return tuple(sorted(expanded))


def suite_plan(catalog: Catalog, names: list[str], *, dependents: bool = False) -> Plan:
    selected = expand_suites(catalog, set(names)) if dependents else tuple(sorted(set(names)))
    for name in selected:
        if name not in catalog.suites:
            raise SelectionError(f"Okänd testgrupp: {name}")
        if catalog.suites[name].status == "planned":
            raise SelectionError(f"{name}: ännu utan tester; ingen verifiering kan utföras")
    tests = tuple(sorted({p for name in selected for p in catalog.suites[name].tests}))
    return Plan(selected, tests, ("Uttryckligt valda grupper" + (" med beroenden" if dependents else ""),))


def full_plan(catalog: Catalog, reasons: tuple[str, ...] = ("Hela den befintliga sviten",)) -> Plan:
    names = tuple(sorted(name for name, suite in catalog.suites.items() if suite.status != "planned"))
    return Plan(names, catalog.tests, reasons, full=True)


def changed_plan(catalog: Catalog, paths: list[str]) -> Plan:
    names: set[str] = set()
    direct: set[str] = set()
    reasons: list[str] = []
    postgres: set[str] = set()
    broad = False
    for path in sorted({relative_path(p) for p in paths}):
        matched = [r for r in catalog.rules if any(fnmatch.fnmatchcase(path, p) for p in r.paths)]
        # Postgres-regler väljer inga grupper; de pekar ut vilka Postgres-prov ändringen berör.
        touched = {s for r in matched for s in r.postgres}
        touched |= {s for s in catalog.markers.get("postgres", ()) if s.split("::")[0] == path}
        if touched:
            postgres |= touched
            reasons.append(f"{path}: berör Postgres-prov")
        matched = [r for r in matched if not r.postgres]
        if path in catalog.tests:
            direct.add(path)
            reasons.append(f"{path}: ändrad testfil väljs direkt")
            if not matched:
                continue
        if not matched:
            broad = True
            reasons.append(f"{path}: okänd påverkan, välj hela sviten")
        elif any(r.full for r in matched):
            broad = True
            reasons.append(f"{path}: gemensam infrastruktur, välj hela sviten")
        else:
            affected = {name for rule in matched for name in rule.suites}
            names.update(affected)
            reasons.append(f"{path}: " + (", ".join(sorted(affected)) if affected else "förklarande dokumentation"))
    if broad:
        # En okänd fil får inte dölja att en samtidigt berörd målgrupp helt saknar tester.
        if names:
            suite_plan(catalog, sorted(names), dependents=True)
        return replace(full_plan(catalog, tuple(reasons)), postgres=tuple(sorted(postgres)))
    plan = suite_plan(catalog, sorted(names), dependents=True)
    if plan.suites:
        reasons.append("Efter beroenden: " + ", ".join(plan.suites))
    return Plan(plan.suites, tuple(sorted(set(plan.tests) | direct)), tuple(reasons),
                postgres=tuple(sorted(postgres)))


def git_changes(root: Path, base: str) -> list[str]:
    if not base or base.startswith("-") or "\0" in base:
        raise SelectionError("Ogiltig Git-basreferens")
    def git(*args: str) -> set[str]:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
        if result.returncode:
            # Visa inte URL:er eller annan godtycklig Git-output i felmeddelandet.
            raise SelectionError("Git-urvalet misslyckades; kontrollera basreferens och repo. Inga tester körda.")
        return set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}
    # Committat sedan förgreningen, stageat/ostageat samt nya otrackade filer.
    # Utan rename-detektering syns både borttagna och nya sökvägen.
    committed = git("diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD", "--")
    working = git("diff", "--name-only", "--no-renames", "-z", "HEAD", "--")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
    return sorted(committed | working | untracked)


def marker_matches(nodeid: str, selector: str) -> bool:
    return nodeid == selector or nodeid.startswith((selector + "::", selector + "["))
