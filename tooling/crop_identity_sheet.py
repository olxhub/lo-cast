#!/usr/bin/env python3
"""Split a regular identity-anchor sheet into consistently sized PNGs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from crop_expression_sheet import (
    border_white_fraction,
    center_square,
    outer_content_span,
    panel_spans,
    select_internal_gutters,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--names", required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--suffix", default="calm")
    parser.add_argument("--inset", type=int, default=3)
    parser.add_argument("--gutter-threshold", type=float, default=0.65)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--manifest-id", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = [item.strip() for item in args.names.split(",") if item.strip()]
    expected = args.columns * args.rows
    if len(names) != expected:
        raise SystemExit(f"Expected {expected} names, received {len(names)}")

    sheet = Image.open(args.sheet).convert("RGB")
    try:
        x_gutters = select_internal_gutters(
            sheet, "x", args.columns, args.gutter_threshold
        )
        y_gutters = select_internal_gutters(
            sheet, "y", args.rows, args.gutter_threshold
        )
        x_outer = outer_content_span(sheet, "x", args.gutter_threshold)
        y_outer = outer_content_span(sheet, "y", args.gutter_threshold)
        x_spans = panel_spans(*x_outer, x_gutters, args.inset)
        y_spans = panel_spans(*y_outer, y_gutters, args.inset)
    except ValueError as error:
        raise SystemExit(f"Gutter detection failed: {error}") from error

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    for index, name in enumerate(names):
        row, column = divmod(index, args.columns)
        source_box = (
            x_spans[column][0],
            y_spans[row][0],
            x_spans[column][1],
            y_spans[row][1],
        )
        cell = center_square(sheet.crop(source_box))
        white_border = border_white_fraction(cell)
        cell = cell.resize((args.size, args.size), Image.Resampling.LANCZOS)

        filename = f"{name.lower()}-{args.suffix}.png"
        destination = args.out_dir / filename
        if destination.exists() and not args.overwrite:
            raise SystemExit(f"Refusing to overwrite existing anchor: {destination}")
        cell.save(destination, optimize=True)
        manifest.append(
            {
                "name": name,
                "file": filename,
                "source_box": source_box,
                "size": [args.size, args.size],
                "source_border_white_fraction": round(white_border, 6),
            }
        )

    manifest_path = args.out_dir / f"{args.manifest_id}-manifest.json"
    if manifest_path.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing manifest: {manifest_path}")
    manifest_path.write_text(
        json.dumps(
            {
                "source": str(args.sheet),
                "grid": [args.columns, args.rows],
                "cropStrategy": "detected-white-gutters",
                "inset": args.inset,
                "gutterThreshold": args.gutter_threshold,
                "xContentSpan": list(x_outer),
                "yContentSpan": list(y_outer),
                "xGutters": [
                    {"start": run.start, "end": run.end, "score": run.score}
                    for run in x_gutters
                ],
                "yGutters": [
                    {"start": run.start, "end": run.end, "score": run.score}
                    for run in y_gutters
                ],
                "outputs": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
