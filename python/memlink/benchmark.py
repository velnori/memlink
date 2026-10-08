"""Synthetic scale measurements; failures and limits are first-class results."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from ._version import __version__
from .context_bundle import handoff_from, verify
from .converter import convert
from .registry import get_reader, get_writer
from .verification import offline_guard, runtime_fingerprint


def peak_rss_bytes() -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("Cannot measure peak working set")
        return int(counters.PeakWorkingSetSize)
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def generate(root: Path, count: int, workflow: str) -> int:
    root.mkdir()
    body = "Synthetic memory only: " + "x" * 80
    if workflow == "migration":
        rows = [{"id": f"synthetic-{i:05d}", "memory": body, "user_id": "synthetic-user"} for i in range(count)]
        (root / "memories.json").write_text(json.dumps({"results": rows}, separators=(",", ":")), encoding="utf-8")
    else:
        (root / "memory").mkdir()
        for i in range(count):
            (root / "memory" / f"synthetic-{i:05d}.md").write_text(body, encoding="utf-8")
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _worker(work: Path, count: int, workflow: str) -> dict:
    source, target = work / "source", work / "output"
    input_bytes = generate(source, count, workflow)
    tracemalloc.start()
    started = time.perf_counter()
    status, reason, output_count = "PASS", None, 0
    with offline_guard() as network:
        try:
            if workflow == "migration":
                receipt = convert(get_reader("mem0"), get_writer("openclaw"), source, target, all=True)["receipt"]
                output_count = receipt["accounting"]["output"]
            else:
                handoff_from(source, target, max_records=count, max_bytes=16 * 1024 * 1024)
                report = verify(target)
                output_count = report["records"]
            if output_count != count:
                raise AssertionError("Output count differs from generated count")
        except Exception as exc:
            status, reason = "FAIL", f"{type(exc).__name__}: {exc}"
            receipt = getattr(exc, "receipt", {})
            if receipt.get("errors"):
                reason += "; " + "; ".join(receipt["errors"])
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "workflow": workflow,
        "records": count,
        "status": status,
        "failure_mode": reason,
        "seconds": round(elapsed, 6),
        "peak_python_bytes": peak,
        "peak_rss_bytes": peak_rss_bytes(),
        "input_bytes": input_bytes,
        "output_bytes": sum(p.stat().st_size for p in target.rglob("*") if p.is_file()),
        "output_records": output_count,
        "network": network,
    }


def run_benchmark(root: Path, sizes=(100, 1000, 10000), timeout=600) -> dict:
    if root.exists():
        raise ValueError("Benchmark requires a new output directory")
    root = root.absolute()
    root.mkdir(parents=True)
    results = []
    for workflow in ("migration", "handoff"):
        for size in sizes:
            work = root / f"{workflow}-{size}"
            work.mkdir()
            command = [
                sys.executable,
                "-m",
                "memlink.benchmark",
                "--worker",
                "--out",
                str(work),
                "--size",
                str(size),
                "--workflow",
                workflow,
            ]
            try:
                process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
                if process.returncode:
                    raise RuntimeError(process.stderr[:1000])
                result = json.loads(process.stdout)
            except subprocess.TimeoutExpired:
                result = {
                    "workflow": workflow,
                    "records": size,
                    "status": "FAIL",
                    "failure_mode": f"Process exceeded {timeout}s timeout",
                }
            except (ValueError, RuntimeError) as exc:
                result = {"workflow": workflow, "records": size, "status": "FAIL", "failure_mode": str(exc)}
            results.append(result)
            print(f"{workflow} {size}: {result['status']}", flush=True)
    report = {
        "schema": "memlink-benchmark",
        "version": "1",
        "tool_version": __version__,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "runtime_sha256": runtime_fingerprint(),
        "runtime_dependency": __import__("yaml").__version__,
        "measurement": (
            "One fresh child per synthetic size/workflow. Peak process RSS/working set includes generation; "
            "tracemalloc peak Python allocation and elapsed time exclude generation. "
            "No unlimited or live-service claim."
        ),
        "results": results,
    }
    (root / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines: list[str] = [
        "# Synthetic benchmark",
        "",
        report["measurement"],
        "",
        "| Workflow | Records | Result | Seconds | Peak Python MiB | Input bytes | Output bytes | Failure |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['workflow']} | {r['records']} | {r['status']} | {r.get('seconds', 'NOT_RUN')} | "
            f"{round(r.get('peak_python_bytes', 0) / 1048576, 2)} | {r.get('input_bytes', 'NOT_RUN')} | "
            f"{r.get('output_bytes', 'NOT_RUN')} | {r.get('failure_mode') or ''} |"
        )
    (root / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sizes", default="100,1000,10000")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--workflow", choices=["migration", "handoff"], default="migration")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_worker(args.out, args.size, args.workflow)))
    else:
        sizes = tuple(int(n) for n in args.sizes.split(","))
        if any(n <= 0 or n > 100000 for n in sizes):
            parser.error("sizes must be between 1 and 100000")
        run_benchmark(args.out, sizes)


if __name__ == "__main__":
    main()
