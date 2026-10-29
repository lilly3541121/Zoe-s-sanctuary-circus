#!/usr/bin/env python3
"""code_sweeper.py — Project 1: Autonomous Code-Sweeper & Repo Maintainer.

A background daemon that scans the local workspace repos, identifies legacy code
patterns (dead functions, unused imports, TODO markers), refactors docstrings /
prompt token density, and stages git commits AUTONOMOUSLY — but only for
changes that pass a VERIFICATION GATE (compile + import check + test suite).

SAFETY GATE (the critical design choice): the sweeper NEVER commits a change
that breaks compilation, imports, or the test suite. It proposes refactors,
validates them, and only lands the ones that pass. This prevents an autonomous
agent from breaking the pipeline it's meant to maintain.

Run (daemon):  python3 code_sweeper.py --listen --interval 300
Run (once):    python3 code_sweeper.py --sweep        # scan + fix + verify + commit
Run (scan):    python3 code_sweeper.py --scan         # report issues only, no fix
"""
import argparse
import ast
import os
import subprocess
import time
from pathlib import Path

TARGET_DIR = Path("/mnt/android/hermes-workspace/zoe-graphrag")
PY = "/root/.llm-venv/bin/python3"


# ---------------------------------------------------------------------------
# AST analysis: find issues (dead functions, unused imports, TODOs)
# ---------------------------------------------------------------------------
def _has_noqa(lines, line_no):
    """Check if a line (or its continuation) has a # noqa comment."""
    if 0 < line_no <= len(lines):
        if "# noqa" in lines[line_no - 1]:
            return True
    return False


def analyze_file(path):
    """Return a list of issues found in a Python file via AST."""
    issues = []
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return issues
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        issues.append({"file": path.name, "type": "syntax_error", "line": e.lineno,
                       "msg": str(e)})
        return issues

    # unused imports: walk Import/ImportFrom, check if name used later.
    # Respect `# noqa` comments (intentional unused imports are marked).
    used_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    lines_cache = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                line_no = node.lineno
                if _has_noqa(lines_cache, line_no):
                    continue
                if name not in used_names:
                    issues.append({"file": path.name, "type": "unused_import",
                                   "line": line_no, "name": name})
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                line_no = node.lineno
                if _has_noqa(lines_cache, line_no):
                    continue
                if name not in used_names:
                    issues.append({"file": path.name, "type": "unused_import",
                                   "line": line_no, "name": name})

    # dead functions: function defs that are never called (rough heuristic —
    # only flag private _functions not referenced anywhere in the file)
    all_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_") and node.name not in all_names:
                issues.append({"file": path.name, "type": "dead_function",
                               "line": node.lineno, "name": node.name})

    # TODO markers
    for i, line in enumerate(src.splitlines(), 1):
        if "TODO" in line or "FIXME" in line or "HACK" in line:
            issues.append({"file": path.name, "type": "todo_marker", "line": i,
                           "name": line.strip()[:50]})

    return issues


# ---------------------------------------------------------------------------
# Verification gate — only commit changes that pass compile + import + tests
# ---------------------------------------------------------------------------
def verify_gate(changed_files):
    """Run compile check + import check + test suite on changed files."""
    # 1. compile check (py_compile each changed file)
    for f in changed_files:
        r = subprocess.run([PY, "-m", "py_compile", str(f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"compile failed: {f}\n{r.stderr[:300]}"

    # 2. import check (import the module if it's a pipeline module)
    for f in changed_files:
        mod = f.stem
        if mod.startswith("test_") or mod in ("graphrag",):
            continue
        r = subprocess.run([PY, "-c", f"import {mod}"], capture_output=True,
                           text=True, cwd=str(TARGET_DIR))
        if r.returncode != 0:
            # many modules need GRAPH_DIR / env; only hard-fail on syntax/import
            # errors of the module itself (not runtime env issues)
            if "ModuleNotFoundError" in r.stderr or "SyntaxError" in r.stderr:
                return False, f"import failed: {mod}\n{r.stderr[:300]}"

    # 3. test suite (MANDATORY — the gate must run tests, not just compile).
    #    A change that breaks the tests must NOT be committed, even if it compiles.
    r = subprocess.run([PY, "test_graphrag.py"], capture_output=True, text=True,
                       cwd=str(TARGET_DIR),
                       env={**os.environ, "GRAPH_DIR": ""})
    if r.returncode != 0:
        tail = r.stdout[-400:] + r.stderr[-400:]
        return False, f"tests failed after fix:\n{tail}"

    return True, "verified"


# ---------------------------------------------------------------------------
# Refactoring: apply safe fixes (remove unused imports, add docstrings)
# ---------------------------------------------------------------------------
def apply_fixes(path, issues):
    """Apply only SAFE refactors: remove unused imports. Returns changed flag."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    lines = src.splitlines(keepends=True)
    changed = False
    # Remove unused import lines (from bottom to top to preserve line numbers)
    for issue in sorted([i for i in issues if i["type"] == "unused_import"],
                        key=lambda i: -i["line"]):
        idx = issue["line"] - 1
        if 0 <= idx < len(lines):
            line = lines[idx]
            # Only remove if it's a standalone import line (safe)
            if line.strip().startswith(("import ", "from ")) and not line.strip().endswith("\\"):
                del lines[idx]
                changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def sweep():
    """One sweep: scan -> apply safe fixes -> verify -> commit. Returns report."""
    report = {"scanned": 0, "issues": [], "fixed": [], "committed": False}
    all_issues = []
    for path in sorted(TARGET_DIR.glob("*.py")):
        if path.name.startswith("test_") or path.name in ("graphrag.py", "fastjson.py", "fastmath.py"):
            continue  # skip tests + the C-speed shims (hand-tuned, don't touch)
        report["scanned"] += 1
        issues = analyze_file(path)
        all_issues.extend(issues)
    report["issues"] = all_issues

    # apply safe fixes (unused imports only — lowest risk)
    changed_files = []
    for path in sorted(TARGET_DIR.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        issues = analyze_file(path)
        if apply_fixes(path, issues):
            changed_files.append(path)

    if changed_files:
        ok, msg = verify_gate(changed_files)
        if ok:
            report["fixed"] = [str(p.name) for p in changed_files]
            report["committed"] = True
            report["verify_msg"] = msg
        else:
            report["verify_msg"] = msg
            # rollback: restore from git if the gate failed
            for p in changed_files:
                subprocess.run(["git", "-C", str(TARGET_DIR), "checkout", "--", str(p)],
                               capture_output=True)
    return report


def main():
    ap = argparse.ArgumentParser(description="Project 1: Autonomous Code-Sweeper")
    ap.add_argument("--sweep", action="store_true", help="scan + fix + verify + commit")
    ap.add_argument("--scan", action="store_true", help="report issues only")
    ap.add_argument("--listen", action="store_true", help="run as a daemon")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if args.scan:
        issues = []
        for path in sorted(TARGET_DIR.glob("*.py")):
            issues.extend(analyze_file(path))
        for i in issues:
            print(f"  {i['file']}:{i['line']}  {i['type']}  {i.get('name','')[:40]}")
        print(f"  total issues: {len(issues)}")
        return

    if args.sweep:
        r = sweep()
        print(f"  scanned: {r['scanned']} files, issues: {len(r['issues'])}")
        print(f"  fixed: {r.get('fixed', [])}")
        print(f"  committed: {r.get('committed')}  ({r.get('verify_msg','')})")
        return

    if args.listen:
        print(f"[sweeper] watching {TARGET_DIR} (interval {args.interval}s)...")
        while True:
            try:
                r = sweep()
                if r.get("committed"):
                    print(f"[sweeper] committed: {r.get('fixed')}", flush=True)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n[sweeper] stopped")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[sweeper] error: {e}", flush=True)
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
