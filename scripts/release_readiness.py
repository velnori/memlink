"""Build and verify a local candidate, recording PASS/FAIL/NOT_RUN honestly.

Does not push, tag, publish, deploy or submit anything. Use a new evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New ignored evidence directory")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--wheelhouse", type=Path, help="Local dependency wheels; default installation has no index")
    parser.add_argument(
        "--fresh-root", type=Path, help="New writable directory outside the checkout (otherwise OS temp)"
    )
    parser.add_argument(
        "--allow-index", action="store_true", help="Allow pip to obtain runtime dependencies from its index"
    )
    parser.add_argument(
        "--audit-online", action="store_true", help="Query public runtime package advisories; separate from core"
    )
    parser.add_argument("--benchmark-sizes", default="100,1000,10000")
    parser.add_argument(
        "--benchmark-evidence",
        type=Path,
        help="Reuse measured JSON only for identical core, runtime dependency, Python and OS",
    )
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists():
        parser.error("Use a new output directory; evidence is never silently reused")
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    temp = output / "temp"
    temp.mkdir()
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    environment["TEMP"] = str(temp)
    environment["TMP"] = str(temp)
    environment["COVERAGE_FILE"] = str(output / ".coverage")
    checks: list[dict] = []
    builds: list[dict] = []
    details: dict = {}

    def run(name, command, cwd=ROOT, env=None, timeout=1200):
        print(name + ": running", flush=True)
        try:
            process = subprocess.run(
                list(map(str, command)),
                cwd=cwd,
                env=env or environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            (logs / (name + ".log")).write_text("TIMEOUT " + str(timeout), encoding="utf-8")
            raise RuntimeError(name + " timed out") from exc
        (logs / (name + ".log")).write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"{name} exit {process.returncode}; see logs/{name}.log")
        return process.stdout

    def check(name, action):
        try:
            action()
            checks.append({"name": name, "status": "PASS", "evidence": "logs/" + name + ".log"})
            print(name + ": PASS", flush=True)
            return True
        except Exception as exc:
            checks.append({"name": name, "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"})
            print(name + ": FAIL " + str(exc), flush=True)
            return False

    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    names = sorted({p.decode("utf-8") for p in listing.split(b"\0") if p})
    source_hashes = {n: sha(ROOT / n) for n in names if (ROOT / n).is_file()}
    source_digest = hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
    (output / "source-files.json").write_text(json.dumps(source_hashes, indent=2), encoding="utf-8")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    stage = output / "public-source"
    stage.mkdir()
    for name in source_hashes:
        destination = stage / name
        if not destination.resolve().is_relative_to(stage.resolve()):
            raise ValueError("Unsafe public snapshot path")
        if name.startswith((".planning/", "docs/relaunch/", "docs/manaul/")):
            raise ValueError("Internal file entered public snapshot: " + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    candidate = output / "candidate-dist"
    candidate.mkdir()
    version_match = re.search(
        r'__version__ = "([^"]+)"', (stage / "python/memlink/_version.py").read_text(encoding="utf-8")
    )
    assert version_match is not None
    version = version_match[1]

    def build():
        run(
            "build",
            [
                sys.executable,
                "-c",
                (
                    "from setuptools.build_meta import build_sdist, build_wheel; "
                    f"build_sdist({str(candidate)!r}); build_wheel({str(candidate)!r})"
                ),
            ],
            cwd=stage,
        )
        archives = sorted(candidate.iterdir())
        assert len(archives) == 2 and any(p.suffix == ".whl" for p in archives)
        for artifact in archives:
            builds.append({"name": artifact.name, "sha256": sha(artifact), "bytes": artifact.stat().st_size})

    built = check("build", build)

    def integrity():
        wheel = next(candidate.glob("*.whl"))
        sdist = next(candidate.glob("*.tar.gz"))
        with zipfile.ZipFile(wheel) as archive:
            members = archive.namelist()
            required = {
                "memlink/py.typed",
                "memlink/resources/canonical-v1.schema.json",
                "memlink/resources/compatibility-manifest-v1.json",
                "memlink/resources/conformance/suite.json",
            }
            assert required.issubset(members)
            assert any(p.endswith("licenses/LICENSE") or p.endswith("/LICENSE") for p in members)
            for path in (stage / "python/memlink").rglob("*"):
                if path.is_file() and path.suffix in {".py", ".json", ".md", ".typed"}:
                    member = path.relative_to(stage / "python").as_posix()
                    assert member in members and archive.read(member) == path.read_bytes(), member
        with tarfile.open(sdist) as archive:
            members = archive.getnames()
            assert any(p.endswith("/scripts/release_readiness.py") for p in members)
            assert any(p.endswith("/docs/guide/releasing.md") for p in members)
            assert not any("/.planning/" in p or "/docs/relaunch/" in p or "/docs/manaul/" in p for p in members)
        rebuilt = output / "sdist-rebuilt"
        rebuilt.mkdir()
        run(
            "sdist-rebuild",
            [
                sys.executable,
                "-m",
                "pip",
                "--no-cache-dir",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                rebuilt,
                sdist,
            ],
            cwd=output,
        )
        with zipfile.ZipFile(wheel) as first, zipfile.ZipFile(next(rebuilt.glob("*.whl"))) as second:
            assert first.namelist() == second.namelist()
            assert all(first.read(name) == second.read(name) for name in first.namelist())
        (logs / "package-integrity.log").write_text(
            "Wheel assets match public snapshot; sdist excludes internal files; "
            "sdist rebuild matches all wheel entries.\n",
            encoding="utf-8",
        )

    if built:
        check("package-integrity", integrity)
    fresh = (
        args.fresh_root.absolute()
        if args.fresh_root
        else Path(tempfile.mkdtemp(prefix="memlink-release-", dir=tempfile.gettempdir()))
    )
    if fresh.resolve().is_relative_to(ROOT.resolve()) or ROOT.resolve().is_relative_to(fresh.resolve()):
        parser.error("Fresh-install root must be outside the checkout and not its ancestor")
    if args.fresh_root:
        fresh.mkdir(parents=True, exist_ok=False)
    fresh_environment = environment.copy()
    fresh_environment["TEMP"] = str(fresh)
    fresh_environment["TMP"] = str(fresh)
    venv = fresh / "venv"
    fresh_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    bin_dir = fresh_python.parent
    fresh_environment["PATH"] = str(bin_dir) + os.pathsep + environment.get("PATH", "")

    def install():
        run("create-venv", [sys.executable, "-m", "venv", venv], cwd=fresh, env=fresh_environment)
        command = [fresh_python, "-m", "pip", "--no-cache-dir", "install"]
        if not args.allow_index:
            command.append("--no-index")
        if args.wheelhouse:
            command.extend(["--find-links", args.wheelhouse.absolute()])
        command.append(next(candidate.glob("*.whl")))
        run("fresh-install", command, cwd=fresh, env=fresh_environment)
        probe = run(
            "fresh-import",
            [
                fresh_python,
                "-c",
                (
                    "import json,sys,memlink,yaml; from importlib.metadata import version; "
                    "print(json.dumps({'package':memlink.__file__,'prefix':sys.prefix,'version':version('memlink-bridge'),'yaml':yaml.__version__}))"
                ),
            ],
            cwd=fresh,
            env=fresh_environment,
        )
        info = json.loads(probe)
        assert Path(info["package"]).is_relative_to(venv) and info["version"] == version
        assert tuple(map(int, info["yaml"].split("."))) >= (6, 0, 3)
        details["fresh_install"] = info

    installed = built and check("fresh-install", install)
    tool_paths = [p for p in sys.path if p and "site-packages" in p]

    def with_tools(module, arguments):
        code = (
            f"import sys,runpy; sys.path.extend({tool_paths!r}); "
            f"sys.argv=[{module!r},*{list(map(str, arguments))!r}]; "
            f"runpy.run_module({module!r},run_name='__main__')"
        )
        return [fresh_python, "-c", code]

    def tests():
        run(
            "tests",
            with_tools(
                "pytest",
                [
                    "tests/",
                    "-q",
                    "-rs",
                    "--cov=memlink",
                    "--cov-report=term",
                    "--cov-report=xml:" + str(output / "coverage.xml"),
                    "--junitxml=" + str(output / "tests.xml"),
                    "--basetemp=" + str(output / "pytest-temp"),
                    "-o",
                    "cache_dir=" + str(output / "pytest-cache"),
                ],
            ),
        )

    check("lint", lambda: run("lint", [sys.executable, "-m", "ruff", "check", "python/memlink", "tests", "scripts"]))
    check(
        "format",
        lambda: run(
            "format", [sys.executable, "-m", "ruff", "format", "--check", "python/memlink", "tests", "scripts"]
        ),
    )
    check(
        "types",
        lambda: run(
            "types", [sys.executable, "-m", "mypy", "--cache-dir", output / "mypy-cache", "python/memlink", "scripts"]
        ),
    )
    if installed:
        check("tests", tests)
        check("docs", lambda: run("docs", with_tools("mkdocs", ["build", "--strict", "--site-dir", output / "site"])))
        conformance_path = fresh / "conformance.json"
        if check(
            "conformance",
            lambda: run(
                "conformance",
                [fresh_python, "-m", "memlink.cli", "conformance", "--report", conformance_path],
                cwd=fresh,
                env=fresh_environment,
            ),
        ):
            report = json.loads(conformance_path.read_text(encoding="utf-8"))
            details["conformance"] = report
            shutil.copy2(conformance_path, output / "conformance.json")
            checks.extend(
                {"name": c["name"], "status": "NOT_RUN", "reason": c["reason"]}
                for c in report["checks"]
                if c["status"] == "NOT_RUN"
            )

        def installed_tamper_probe():
            probe = venv / (
                "Lib/site-packages/memlink/resources/conformance/README.md"
                if os.name == "nt"
                else (
                    f"lib/python{platform.python_version().rsplit('.', 1)[0]}"
                    "/site-packages/memlink/resources/conformance/README.md"
                )
            )
            assert probe.resolve().is_relative_to(venv.resolve())
            original = probe.read_bytes()
            try:
                probe.write_bytes(original + b"\nSynthetic package tampering probe.\n")
                process = subprocess.run(
                    [fresh_python, "-m", "memlink.cli", "conformance", "--adapter", "generic"],
                    cwd=fresh,
                    env=fresh_environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=180,
                )
                (logs / "installed-package-tamper.log").write_text(process.stdout + process.stderr, encoding="utf-8")
                tampered = json.loads(process.stdout)
                assert process.returncode == 2 and tampered["status"] == "FAIL"
                assert any(
                    c["name"] == "core:installed-package-integrity" and c["status"] == "FAIL"
                    for c in tampered["checks"]
                )
            finally:
                probe.write_bytes(original)
            assert probe.read_bytes() == original

        check("installed-package-tamper", installed_tamper_probe)
        check(
            "fresh-workflows-demo",
            lambda: run(
                "fresh-workflows-demo",
                [fresh_python, "-m", "memlink.demo", "--out", fresh / "demo"],
                cwd=fresh,
                env=fresh_environment,
            ),
        )
        demo_path = fresh / "demo/demo-results.json"
        if demo_path.exists():
            shutil.copy2(demo_path, output / "demo-results.json")
            shutil.copy2(fresh / "demo/recording.md", output / "demo-recording.md")

        example_blocks = re.findall(
            r"<!-- release-example -->\s*```sh\n(.*?)```", (stage / "README.md").read_text(encoding="utf-8"), re.S
        )
        assert len(example_blocks) == 2
        shell_binary = shutil.which("bash")
        # Windows' System32 bash.exe is a WSL launcher, not the configured Git
        # Bash used by native Python/venv examples. Reuse Git's bundled shell.
        if os.name == "nt" and (git_binary := shutil.which("git")):
            git_bash = Path(git_binary).resolve().parents[1] / "bin/bash.exe"
            if git_bash.is_file():
                shell_binary = str(git_bash)
        for label, binary in (
            ("shell", shell_binary),
            ("powershell", shutil.which("pwsh") or shutil.which("powershell")),
        ):
            if not binary:
                checks.append({"name": "examples-" + label, "status": "NOT_RUN", "reason": "Shell not available"})
                continue
            example_root = fresh / ("examples-" + label)
            example_root.mkdir()
            script = example_root / ("readme.sh" if label == "shell" else "readme.ps1")
            content = "\n".join(example_blocks)
            if label == "shell":
                script.write_text("set -euo pipefail\n" + content, encoding="utf-8", newline="")
                command = [binary, script]
            else:
                content = "\n".join(
                    line + "\nif ($LASTEXITCODE -ne 0) { throw 'README command failed' }"
                    for line in content.splitlines()
                    if line.strip()
                )
                script.write_text("$ErrorActionPreference = 'Stop'\n" + content, encoding="utf-8", newline="")
                command = [binary, "-NoProfile", "-File", script]
            check(
                "examples-" + label,
                lambda c=command, p=example_root: run(
                    "examples-" + p.name.split("-", 1)[1], c, cwd=p, env=fresh_environment
                ),
            )
            wrapper = stage / "scripts" / ("demo.sh" if label == "shell" else "demo.ps1")
            wrapper_out = fresh / ("wrapper-" + label)
            demo_env = fresh_environment.copy()
            demo_env["MEMLINK_PYTHON"] = str(fresh_python)
            command = (
                [binary, wrapper, wrapper_out]
                if label == "shell"
                else [binary, "-NoProfile", "-File", wrapper, "-OutputDirectory", wrapper_out, "-Python", fresh_python]
            )
            check("demo-" + label, lambda c=command, e=demo_env, n=label: run("demo-" + n, c, cwd=fresh, env=e))
        if args.benchmark_evidence:

            def reuse_benchmark():
                prior = json.loads(args.benchmark_evidence.read_text(encoding="utf-8"))
                fingerprint = json.loads(
                    run(
                        "benchmark-identity",
                        [
                            fresh_python,
                            "-c",
                            "import json,yaml; from memlink.verification import runtime_fingerprint; "
                            "print(json.dumps({'core':runtime_fingerprint(),'yaml':yaml.__version__}))",
                        ],
                        cwd=fresh,
                        env=fresh_environment,
                    )
                )
                assert prior["runtime_sha256"] == fingerprint["core"]
                assert prior["runtime_dependency"] == fingerprint["yaml"]
                assert prior["python"] == platform.python_version() and prior["os"] == platform.system()
                sizes = {int(n) for n in args.benchmark_sizes.split(",")}
                assert {(r["workflow"], r["records"]) for r in prior["results"]} == {
                    (w, n) for w in ("migration", "handoff") for n in sizes
                }
                assert all(
                    r.get("network", {}).get("canary") and r["network"]["attempts"] == 0 for r in prior["results"]
                )
                destination = fresh / "benchmark"
                destination.mkdir()
                shutil.copy2(args.benchmark_evidence, destination / "benchmark.json")
                shutil.copy2(args.benchmark_evidence.with_suffix(".md"), destination / "benchmark.md")
                (logs / "benchmark-measured.log").write_text(
                    "Reused identical measured core/environment: " + str(args.benchmark_evidence.absolute()),
                    encoding="utf-8",
                )

            check("benchmark-measured", reuse_benchmark)
        else:
            check(
                "benchmark-measured",
                lambda: run(
                    "benchmark-measured",
                    [
                        fresh_python,
                        "-m",
                        "memlink.benchmark",
                        "--out",
                        fresh / "benchmark",
                        "--sizes",
                        args.benchmark_sizes,
                    ],
                    cwd=fresh,
                    env=fresh_environment,
                    timeout=2400,
                ),
            )
        benchmark_path = fresh / "benchmark/benchmark.json"
        if benchmark_path.exists():
            details["benchmark"] = json.loads(benchmark_path.read_text(encoding="utf-8"))
            shutil.copy2(benchmark_path, output / "benchmark.json")
            shutil.copy2(fresh / "benchmark/benchmark.md", output / "benchmark.md")
        if check(
            "security",
            lambda: run(
                "security",
                [
                    sys.executable,
                    stage / "scripts/security_checks.py",
                    "--out",
                    output / "security.json",
                    "--python",
                    fresh_python,
                    *(["--online"] if args.audit_online else []),
                ],
            ),
        ):
            security = json.loads((output / "security.json").read_text(encoding="utf-8"))
            details["security"] = security
            if security["dependencies"]["status"] == "NOT_RUN":
                checks.append(
                    {
                        "name": "dependency-advisories",
                        "status": "NOT_RUN",
                        "reason": "Advisory query unavailable or not requested",
                    }
                )

        def schema_oracle():
            code = (
                f"import sys,json,pathlib; sys.path.extend({tool_paths!r}); "
                "import jsonschema; from importlib.resources import files; "
                "r=files('memlink').joinpath('resources'); "
                "schemas={p.name:json.loads(p.read_text()) for p in r.iterdir() if p.name.endswith('.schema.json')}; "
                "[jsonschema.Draft202012Validator.check_schema(s) for s in schemas.values()]; "
                f"root=pathlib.Path({str(fresh / 'demo')!r}); "
                "jsonschema.validate(json.loads((root/'migration/.memlink/receipt.json').read_text()),"
                "schemas['memlink-receipt-v1.schema.json']); "
                "jsonschema.validate(json.loads((root/'migration/.memlink/archive.json').read_text()),"
                "schemas['memlink-archive-v1.schema.json']); "
                "jsonschema.validate(json.loads((root/'all/manifest.json').read_text()),"
                "schemas['memlink-context-bundle-v1.schema.json']); "
                "print('Independent draft 2020-12 schemas and actual installed artifacts: PASS')"
            )
            run("schema-oracle", [fresh_python, "-c", code], cwd=fresh, env=fresh_environment)

        check("schema-oracle", schema_oracle)
    else:
        for name in (
            "tests",
            "docs",
            "conformance",
            "installed-package-tamper",
            "fresh-workflows-demo",
            "benchmark-measured",
            "security",
            "schema-oracle",
            "examples-shell",
            "examples-powershell",
            "demo-shell",
            "demo-powershell",
        ):
            checks.append({"name": name, "status": "NOT_RUN", "reason": "Fresh installation prerequisite failed"})

    def unchanged():
        assert source_hashes == {n: sha(ROOT / n) for n in source_hashes}, "Source changed during readiness"
        (logs / "source-unchanged.log").write_text(source_digest + "\n", encoding="utf-8")

    check("source-unchanged", unchanged)
    if built:

        def copy_candidate():
            args.dist.mkdir(parents=True, exist_ok=True)
            for artifact in candidate.iterdir():
                destination = args.dist / artifact.name
                if destination.exists():
                    assert sha(destination) == sha(artifact), (
                        "Different existing candidate preserved; choose --dist NEW_PATH"
                    )
                else:
                    shutil.copy2(artifact, destination)
            (logs / "local-candidate.log").write_text(str(args.dist.absolute()), encoding="utf-8")

        check("local-candidate", copy_candidate)
    checks.append(
        {
            "name": "remote-ci-current-candidate",
            "status": "NOT_RUN",
            "reason": "No push/PR/tag or remote execution authorized by this local command",
        }
    )
    checks.append(
        {
            "name": "real-users-and-model-consumers",
            "status": "NOT_RUN",
            "reason": "Synthetic engineering evidence is not adoption or model memory verification",
        }
    )
    local_status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    matrix = [
        {
            "os": system,
            "python": python,
            "status": "PASS"
            if system == platform.system()
            and python == platform.python_version().rsplit(".", 1)[0]
            and local_status == "PASS"
            else "NOT_RUN",
        }
        for system in ("Windows", "Linux", "Darwin")
        for python in ("3.10", "3.11", "3.12")
    ]
    tools = {}
    for name in ("setuptools", "pytest", "pytest-cov", "ruff", "mypy", "mkdocs-material", "jsonschema"):
        try:
            tools[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            tools[name] = "NOT_RUN"
    report = {
        "schema": "memlink-release-readiness",
        "version": "1",
        "package_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "working_tree_dirty": dirty,
        "public_source_sha256": source_digest,
        "public_source_files": "source-files.json",
        "tools": tools,
        "local_status": local_status,
        "release_authorized": False,
        "counts": {s: sum(c["status"] == s for c in checks) for s in ("PASS", "FAIL", "NOT_RUN")},
        "builds": builds,
        "checks": checks,
        "environment_matrix": matrix,
        "compatibility_manifest": json.loads(
            (stage / "python/memlink/resources/compatibility-manifest-v1.json").read_text(encoding="utf-8")
        ),
        "workflows": {
            "full_migration": "fresh-workflows-demo",
            "handoff_all_and_selective": "fresh-workflows-demo",
            "adapter_conformance": "conformance",
        },
        "details": details,
    }
    (output / "readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Local release readiness",
        "",
        f"Local result: **{local_status}**. Release authorization: **false**.",
        "",
        f"Package {version}; commit {commit}; public working-tree SHA256 {source_digest}.",
        "",
        "| Check | Result | Evidence / reason |",
        "|---|---|---|",
    ]
    lines.extend(f"| {c['name']} | {c['status']} | {c.get('reason', c.get('evidence', ''))} |" for c in checks)
    lines += ["", "## Build hashes", ""]
    lines.extend(f"- {b['name']}: `{b['sha256']}` ({b['bytes']} bytes)" for b in builds)
    lines += ["", "## Environments", "", "| OS | Python | Result |", "|---|---|---|"]
    lines.extend(f"| {m['os']} | {m['python']} | {m['status']} |" for m in matrix)
    (output / "readiness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Readiness: " + local_status + " -> " + str(output / "readiness.json"), flush=True)
    raise SystemExit(1 if local_status == "FAIL" else 0)


if __name__ == "__main__":
    main()
