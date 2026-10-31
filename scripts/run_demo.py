"""Runs the demo process from the command line.

Usage:
    python scripts\\run_demo.py --source sandbox\\a.txt [--extra sandbox\\b.txt]
"""

import argparse
import sys
from pathlib import Path

from engops.app.config import Settings
from engops.app.context import create_context
from engops.app.paths import AppPaths, data_root
from engops.domain.errors import RecordNotFoundError
from engops.process_runtime.demo import DEMO_SLUG
from engops.process_runtime.errors import ProcessRuntimeError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the demo process.")
    parser.add_argument("--source", required=True, type=Path, help="source .txt or .csv file")
    parser.add_argument("--extra", type=Path, help="optional second file to compare with")
    args = parser.parse_args(argv)

    paths = AppPaths(data_root())
    paths.ensure()
    ctx = create_context(paths, Settings.load(paths.config_file))
    try:
        inputs = {"source": args.source}
        if args.extra is not None:
            inputs["extra"] = args.extra
        try:
            result = ctx.runner.run(DEMO_SLUG, inputs, on_log=print)
        except (ProcessRuntimeError, RecordNotFoundError) as exc:
            print(f"Cannot run: {exc}")
            return 2

        run = result.run
        print()
        print(f"Status:  {run.status.label}")
        print(f"Summary: {run.summary}")
        for warning in run.warnings:
            print(f"Warning: {warning}")
        if run.error:
            print(f"Error:   {run.error}")
        for artifact in result.artifacts:
            stored = ctx.stored_files.get(artifact.stored_file_id)
            print(f"Output [{artifact.role}]: {ctx.files.path_of(stored)}")
        return 0 if result.ok else 1
    finally:
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())