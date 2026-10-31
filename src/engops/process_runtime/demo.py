"""A harmless demo process used to exercise the runtime end to end."""

from __future__ import annotations

from engops.process_runtime.contracts import BaseProcessHandler, ProcessContext

DEMO_SLUG = "demo_echo"

DEMO_MANIFEST = {
    "inputs": [
        {
            "role": "source",
            "label": "Source text file",
            "required": True,
            "extensions": [".txt", ".csv"],
            "description": "The file to summarize.",
        },
        {
            "role": "extra",
            "label": "Second text file",
            "required": False,
            "extensions": [".txt", ".csv"],
            "description": "Optional file to compare with the source.",
        },
    ],
    "outputs": [
        {"role": "summary", "label": "Summary", "required": True},
        {"role": "comparison", "label": "Comparison", "required": False},
    ],
    "operations": [
        {"id": "summarize", "label": "Summarize source", "requires": ["source"]},
        {"id": "compare", "label": "Compare with second file", "requires": ["source", "extra"]},
    ],
}


class DemoEchoHandler(BaseProcessHandler):
    slug = DEMO_SLUG

    def run(self, ctx: ProcessContext) -> None:
        ctx.log("Reading the source file")
        source_text = ctx.input_path("source").read_text(encoding="utf-8", errors="replace")
        source_lines = source_text.splitlines()
        words = source_text.split()
        ctx.check_cancelled()

        if not words:
            ctx.warn("The source file contains no words.")

        if ctx.operation_enabled("summarize"):
            out = ctx.new_output_path("summary.txt")
            out.write_text(
                f"Lines: {len(source_lines)}\nWords: {len(words)}\nCharacters: {len(source_text)}\n",
                encoding="utf-8",
            )
            ctx.add_output("summary", out)
            ctx.log("Summary written")
        ctx.check_cancelled()

        if ctx.operation_enabled("compare"):
            other_text = ctx.input_path("extra").read_text(encoding="utf-8", errors="replace")
            other_lines = other_text.splitlines()
            only_source = [line for line in source_lines if line not in set(other_lines)]
            only_other = [line for line in other_lines if line not in set(source_lines)]
            out = ctx.new_output_path("comparison.txt")
            out.write_text(
                f"Source lines: {len(source_lines)}\n"
                f"Second file lines: {len(other_lines)}\n"
                f"Lines only in source: {len(only_source)}\n"
                f"Lines only in second file: {len(only_other)}\n",
                encoding="utf-8",
            )
            ctx.add_output("comparison", out)
            ctx.log("Comparison written")