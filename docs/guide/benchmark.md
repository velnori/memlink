# Reproducible synthetic benchmark

Run the installed candidate using only invented data:

```sh
python -m memlink.benchmark --out synthetic-benchmark
```

The fixed generator measures **100 / 1,000 / 10,000 records** for two workflows: scoped offline Mem0 JSON → OpenClaw Full Migration; and plain OpenClaw notes → all-record Context Handoff. Bodies are invented 103-byte ASCII strings with deterministic IDs. Each case uses a fresh child process. This measures file operations, not live application or model-retrieval behavior.

`benchmark.json` / `benchmark.md` record elapsed time, peak Python allocation, **peak process RSS/working set**, input/output sizes, actual output count, failures and a tested no-network canary. Generation is excluded from conversion time/Python allocation tracking; process RSS includes generation. Failures remain visible; no extrapolated measurements replace missing results.

For this generator, **1,000 records is the largest completed tested size**. The 10,000-record cases hit output archive/bundle resource limits. Configured ceilings of 100,000 records or 10,000 files do not guarantee that complete transport output fits. Opaque fields, body size and serialization nodes can lower the usable size. Use scoped batches with independent receipts; no unlimited claim is made.

Handoff normally defaults to 1,000 records / 1 MiB of UTF-8 text. The benchmark explicitly raises its text budget; this does not disable verification or the overall 16 MiB/file and serialization limits. Failed cases do not commit an output.

Candidate measurements and environment appear below after verification. Other OS/Python, remote CI and consumer models remain **NOT_RUN** without their own evidence. Readiness can pass its measurement gate while reporting a 10,000-record failure: the recorded failure and public limit are part of the result.

A new run requires a new directory. Reuse is allowed only when core content fingerprint, PyYAML, Python/OS and requested sizes match; readiness verifies all of these.

## Local candidate measurements

Measured 2026-10-04 21:41:46 America/Tijuana (2026-10-05 04:41:46 UTC), Windows / Python 3.12.9 / PyYAML 6.0.3. Single runs with tracemalloc enabled; timing is not a throughput promise. Peak RSS is whole-process peak; allocation peak is Python-only.

| Workflow | Records | Result | Seconds | Peak RSS MiB | Peak Python MiB | Input bytes | Output bytes |
|---|---:|---|---:|---:|---:|---:|---:|
| Full Migration | 100 | PASS | 0.749 | 46.09 | 8.95 | 16,713 | 1,169,833 |
| Full Migration | 1,000 | PASS | 4.599 | 164.85 | 61.89 | 167,013 | 11,675,543 |
| Full Migration | 10,000 | FAIL | 38.653 | 653.90 | 284.87 | 1,670,013 | 0 |
| Handoff all | 100 | PASS | 9.317 | 40.32 | 6.94 | 10,300 | 258,140 |
| Handoff all | 1,000 | PASS | 128.970 | 103.36 | 33.00 | 103,000 | 2,548,652 |
| Handoff all | 10,000 | FAIL | 303.582 | 301.60 | 135.72 | 1,030,000 | 0 |

The migration failure reports `TransactionError: Oversized or hardlinked JSON input` while processing generated transport output; the source is a single regular 1.67 MB JSON file. Handoff reports `TransactionError: Bundle export failed; owned output rolled back`; a separate cause probe confirms `BoundaryError: Input resource limit exceeded`. A 10,000-note source leaves no file-count headroom for its private bundle's records/inventory/report/manifest control files. Neither failure commits output. The disclosure boundary is the largest completed tested size of 1,000 for this exact generator and explicit budgets; arbitrary larger sizes and other environments are NOT_RUN.


The generator/core content fingerprint for this measurement is `dc78574715d78bb653a3b22e666de4506a754a7ca0fc4e846c77d1feca83cce5`. Readiness checks it against the installed wheel before reusing the report. All six network canaries were active and each workflow made zero intercepted network attempts.
