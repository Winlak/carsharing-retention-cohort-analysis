"""Make the executed portfolio notebook deterministic without clearing useful results.

``nbconvert --execute`` injects cell-level IOPub timestamps and kernel-version
metadata. These change on every run even when the data, code and visible result
are identical. This script keeps table/text outputs and execution counts, while
removing volatile metadata. Static figures remain available as versioned PNGs
in ``figures/``; their inline notebook copies are removed to avoid
platform-specific binary diffs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat

CANONICAL_NOTEBOOK_METADATA = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/svg+xml", "application/pdf"}


def normalize_notebook(path: Path) -> None:
    """Strip run-specific metadata and inline plot binaries from an executed notebook."""
    notebook = nbformat.read(path, as_version=4)
    notebook.metadata = CANONICAL_NOTEBOOK_METADATA.copy()

    for index, cell in enumerate(notebook.cells, start=1):
        # ``nbformat.v4.new_*_cell`` generates random IDs.  Stable IDs make a
        # freshly assembled notebook byte-for-byte reproducible as well.
        cell["id"] = f"retention-{index:02d}"
        cell.metadata = {}
        normalized_outputs = []
        for output in cell.get("outputs", []):
            if output.output_type == "display_data" and IMAGE_MIME_TYPES.intersection(
                output.get("data", {})
            ):
                # The full-resolution, versioned image lives in figures/. The
                # corresponding notebook cell still executes, and its useful
                # numerical/table outputs are preserved in other cells.
                continue
            # The notebook schema requires metadata for rich outputs. An empty
            # mapping is canonical and removes execution-specific values.
            if output.output_type in {"display_data", "execute_result", "update_display_data"}:
                output["metadata"] = {}
            else:
                output.pop("metadata", None)
            normalized_outputs.append(output)
        if "outputs" in cell:
            cell.outputs = normalized_outputs

    nbformat.write(notebook, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize volatile Jupyter execution metadata.")
    parser.add_argument("path", type=Path, help="Executed .ipynb file to normalize")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalize_notebook(args.path)
    print(f"Normalized {args.path}")


if __name__ == "__main__":
    main()
