"""Registers the demo process (with its real manifest) in the local database.

Safe to run repeatedly. Adds version 0.2.0 only if it is missing.
"""

from engops.app.config import Settings
from engops.app.context import create_context
from engops.app.paths import AppPaths, data_root
from engops.process_runtime.demo import DEMO_MANIFEST, DEMO_SLUG

DEMO_VERSION = "0.2.0"


def main() -> None:
    paths = AppPaths(data_root())
    paths.ensure()
    ctx = create_context(paths, Settings.load(paths.config_file))
    try:
        process = ctx.processes.get_by_slug(DEMO_SLUG)
        if process is None:
            process = ctx.catalog.register_process(
                slug=DEMO_SLUG,
                name="Demo: echo inputs",
                purpose="Placeholder process used to test the platform. Summarizes a text file.",
                owner="Platform team",
            )
            print(f"Registered process '{DEMO_SLUG}'.")

        existing = {v.version for v in ctx.versions.list_for_process(process.id)}
        if DEMO_VERSION not in existing:
            version = ctx.catalog.add_version(process.id, DEMO_VERSION, DEMO_MANIFEST)
            ctx.catalog.approve_version(version.id, "seed script")
            print(f"Added and approved version {DEMO_VERSION}.")
        else:
            print(f"Version {DEMO_VERSION} already exists.")

        print(f"Database: {paths.db_file}")
        print(f"Processes: {ctx.processes.count()}  |  Runs: {ctx.runs.count()}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()