"""CLI entry point — argparse-based command routing."""

from __future__ import annotations

import sys
from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    DIFF_FOUND = 1
    VALIDATION_ERROR = 2
    IO_ERROR = 3
    CONCURRENT_MODIFICATION = 4
    FORMAT_INCOMPATIBLE = 5
    USER_ABORT = 130


def main() -> None:
    """Entry point for the `memlink` command."""
    # TODO: Phase 3 — argparse full CLI
    print("memlink — AI Memory Interchange Layer")
    print("CLI coming in Phase 3.")


if __name__ == "__main__":
    main()
