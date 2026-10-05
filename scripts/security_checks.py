"""Bounded static policy and optional public dependency advisory check.

This is not a comprehensive security audit. Advisory requests contain only public
package names/versions. No fixtures, local paths or user data are uploaded.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def static_checks(root: Path) -> dict:
    findings = []
    scanned = []
    for path in sorted((root / "python/memlink").glob("*.py")):
        scanned.append(path.relative_to(root).as_posix())
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                findings.append({"file": scanned[-1], "line": node.lineno, "rule": "dynamic-code"})
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"requests", "httpx", "aiohttp", "openai", "anthropic"}:
                        findings.append({"file": scanned[-1], "line": node.lineno, "rule": "core-network-sdk"})
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "yaml"
                and node.func.attr == "load"
            ):
                safe_loader = any(
                    k.arg == "Loader" and isinstance(k.value, ast.Name) and k.value.id == "_UniqueLoader"
                    for k in node.keywords
                )
                if not safe_loader:
                    findings.append({"file": scanned[-1], "line": node.lineno, "rule": "unsafe-yaml-loader"})
    loader = (root / "python/memlink/_frontmatter.py").read_text(encoding="utf-8")
    if "class _UniqueLoader(yaml.SafeLoader)" not in loader:
        findings.append({"file": "python/memlink/_frontmatter.py", "rule": "safe-loader-base"})
    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for workflow in (root / ".github/workflows").glob("*.yml"):
        for action in re.findall(r"uses:\s*([^\s#]+)", workflow.read_text(encoding="utf-8")):
            if not re.fullmatch(r"[^@]+@[0-9a-f]{40}", action):
                findings.append(
                    {"file": workflow.relative_to(root).as_posix(), "rule": "unpinned-action", "action": action}
                )
    if "pull_request_target" in release or "secrets." in release:
        findings.append({"file": ".github/workflows/release.yml", "rule": "release-credential-boundary"})
    if "id-token: write" not in release or "name: pypi" not in release:
        findings.append({"file": ".github/workflows/release.yml", "rule": "trusted-publishing-environment"})
    return {
        "status": "FAIL" if findings else "PASS",
        "scanned_core_files": scanned,
        "findings": findings,
        "limits": (
            "AST checks for dynamic execution/network SDKs/YAML loaders and workflow pins only; "
            "not a general vulnerability scanner or hostile-plugin audit."
        ),
    }


def dependency_check(python: str, online: bool) -> dict:
    process = subprocess.run(
        [
            python,
            "-c",
            "import json; from importlib.metadata import version; print(json.dumps({'PyYAML': version('PyYAML')}))",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    dependencies = json.loads(process.stdout)
    if not online:
        return {
            "status": "NOT_RUN",
            "dependencies": dependencies,
            "reason": "No current advisory query requested; dependency metadata is not an audit",
        }
    checked = []
    for name, version in dependencies.items():
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.load(response)
            vulnerabilities = data["vulnerabilities"]
            checked.append(
                {
                    "name": name,
                    "version": version,
                    "source": url,
                    "vulnerabilities": vulnerabilities,
                    "status": "FAIL" if vulnerabilities else "PASS",
                }
            )
        except (OSError, ValueError, KeyError) as exc:
            checked.append(
                {"name": name, "version": version, "source": url, "status": "NOT_RUN", "reason": type(exc).__name__}
            )
    status = (
        "FAIL"
        if any(d["status"] == "FAIL" for d in checked)
        else "NOT_RUN"
        if any(d["status"] == "NOT_RUN" for d in checked)
        else "PASS"
    )
    return {
        "status": status,
        "checked": checked,
        "scope": (
            "Installed runtime PyYAML against PyPI published advisories; no guarantee of unknown vulnerabilities; "
            "build/dev tools are outside this advisory scope"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    report: dict = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "static": static_checks(ROOT),
        "dependencies": dependency_check(args.python, args.online),
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if any(report[k]["status"] == "FAIL" for k in ("static", "dependencies")) else 0)


if __name__ == "__main__":
    main()
