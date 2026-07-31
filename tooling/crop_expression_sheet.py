#!/usr/bin/env python3
"""Split a regular avatar expression sheet into consistently sized PNGs."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import pstdev

from PIL import Image


@dataclass(frozen=True)
class Run:
    start: int
    end: int
    score: float

    @property
    def center(self) -> float:
        return (self.start + self.end - 1) / 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--expressions", required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument(
        "--sheet-id",
        help="Optional manifest suffix, such as 'core' or 'expressive'.",
    )
    parser.add_argument(
        "--inset",
        type=int,
        default=3,
        help="Pixels removed inside every detected panel edge before squaring.",
    )
    parser.add_argument(
        "--gutter-threshold",
        type=float,
        default=0.65,
        help="Required near-white fraction for a separator row or column.",
    )
    parser.add_argument(
        "--vertical-anchor",
        choices=("center", "top", "bottom"),
        default="center",
        help="Vertical anchor used when a detected panel is taller than square.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of existing outputs. Prefer a staging directory.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def near_white(pixel: tuple[int, ...]) -> bool:
    red, green, blue = pixel[:3]
    return red >= 242 and green >= 242 and blue >= 238


def white_fraction(image: Image.Image, axis: str, index: int) -> float:
    if axis == "x":
        pixels = (image.getpixel((index, y)) for y in range(image.height))
        total = image.height
    else:
        pixels = (image.getpixel((x, index)) for x in range(image.width))
        total = image.width
    return sum(1 for pixel in pixels if near_white(pixel)) / total


def separator_score(image: Image.Image, axis: str, index: int) -> float:
    if axis == "x":
        pixels = [image.getpixel((index, y)) for y in range(image.height)]
    else:
        pixels = [image.getpixel((x, index)) for x in range(image.width)]
    lightness = [sum(pixel[:3]) / 3 for pixel in pixels]
    mean = sum(lightness) / len(lightness)
    deviation = pstdev(lightness)
    white_score = sum(1 for pixel in pixels if near_white(pixel)) / len(pixels)

    # Image generators sometimes render separators as cream rather than white.
    # A separator remains unusually pale and uniform across the complete sheet.
    # Generated sheets render nominally cream dividers anywhere from pale cream
    # to medium beige. Low variance across the complete row or column is the
    # stronger signal: textured portrait backgrounds vary substantially.
    uniform_pale_score = mean / 255 if mean >= 200 and deviation <= 9 else 0.0
    return max(white_score, uniform_pale_score)


def mostly_gutter(image: Image.Image, axis: str, index: int) -> bool:
    """Return true when a row/column is predominantly near-white divider pixels."""
    return white_fraction(image, axis, index) >= 0.88


def candidate_gutter_runs(
    image: Image.Image, axis: str, threshold: float
) -> list[Run]:
    length = image.width if axis == "x" else image.height
    scores = [separator_score(image, axis, index) for index in range(length)]
    runs: list[Run] = []
    start: int | None = None

    for index, score in enumerate(scores):
        if score >= threshold and start is None:
            start = index
        at_end = index == length - 1
        if start is not None and (score < threshold or at_end):
            end = index + 1 if at_end and score >= threshold else index
            runs.append(Run(start, end, max(scores[start:end])))
            start = None
    return runs


def coalesce_gutter_runs(runs: list[Run], length: int) -> list[Run]:
    """Join divider fragments separated by only a few painted pixels."""
    if not runs:
        return []

    maximum_gap = max(3, round(length * 0.003))
    merged = [runs[0]]
    for run in runs[1:]:
        previous = merged[-1]
        if run.start - previous.end <= maximum_gap:
            merged[-1] = Run(
                previous.start,
                run.end,
                max(previous.score, run.score),
            )
        else:
            merged.append(run)
    return merged


def select_internal_gutters(
    image: Image.Image,
    axis: str,
    panel_count: int,
    threshold: float,
) -> list[Run]:
    """Select one detected white run near every expected internal division."""
    length = image.width if axis == "x" else image.height
    edge_margin = max(8, round(length * 0.015))
    candidates = [
        run
        for run in coalesce_gutter_runs(
            candidate_gutter_runs(image, axis, threshold), length
        )
        if run.start > edge_margin and run.end < length - edge_margin
    ]
    if len(candidates) == panel_count - 1:
        return candidates

    selected: list[Run] = []
    tolerance = length / panel_count * 0.38

    for division in range(1, panel_count):
        expected = length * division / panel_count
        available = [run for run in candidates if run not in selected]
        if not available:
            raise ValueError(
                f"No {axis}-axis gutter candidates for division {division}"
            )
        closest = min(available, key=lambda run: abs(run.center - expected))
        distance = abs(closest.center - expected)
        if distance > tolerance:
            raise ValueError(
                f"{axis}-axis gutter {division} is {distance:.1f}px from its "
                f"expected neighborhood; refusing fixed-grid fallback"
            )
        selected.append(closest)

    selected.sort(key=lambda run: run.start)
    if len(selected) != panel_count - 1:
        raise ValueError(
            f"Expected {panel_count - 1} internal {axis}-gutters, "
            f"found {len(selected)}"
        )
    return selected


def outer_content_span(
    image: Image.Image, axis: str, threshold: float
) -> tuple[int, int]:
    length = image.width if axis == "x" else image.height
    edge_margin = max(8, round(length * 0.015))
    runs = coalesce_gutter_runs(
        candidate_gutter_runs(image, axis, threshold), length
    )
    content_start = (
        runs[0].end if runs and runs[0].start <= edge_margin else 0
    )
    content_end = (
        runs[-1].start if runs and runs[-1].end >= length - edge_margin else length
    )
    if content_end <= content_start:
        raise ValueError(f"Outer {axis}-gutters leave no content")
    return content_start, content_end


def panel_spans(
    content_start: int,
    content_end: int,
    gutters: list[Run],
    inset: int,
) -> list[tuple[int, int]]:
    raw = [(content_start, gutters[0].start)]
    raw.extend(
        (left.end, right.start) for left, right in zip(gutters, gutters[1:])
    )
    raw.append((gutters[-1].end, content_end))

    spans: list[tuple[int, int]] = []
    for start, end in raw:
        safe_start = start + inset
        safe_end = end - inset
        if safe_end <= safe_start:
            raise ValueError(f"Inset {inset}px collapses panel span {start}:{end}")
        spans.append((safe_start, safe_end))
    return spans


def trim_gutters(image: Image.Image, maximum: int = 8) -> Image.Image:
    left = 0
    while left < min(maximum, image.width - 1) and mostly_gutter(image, "x", left):
        left += 1

    right = image.width
    while (
        right > max(left + 1, image.width - maximum)
        and mostly_gutter(image, "x", right - 1)
    ):
        right -= 1

    top = 0
    while top < min(maximum, image.height - 1) and mostly_gutter(image, "y", top):
        top += 1

    bottom = image.height
    while (
        bottom > max(top + 1, image.height - maximum)
        and mostly_gutter(image, "y", bottom - 1)
    ):
        bottom -= 1

    return image.crop((left, top, right, bottom))


def center_square(
    image: Image.Image, vertical_anchor: str = "center"
) -> Image.Image:
    side = min(image.width, image.height)
    left = (image.width - side) // 2
    if vertical_anchor == "top":
        top = 0
    elif vertical_anchor == "bottom":
        top = image.height - side
    else:
        top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def border_white_fraction(image: Image.Image) -> float:
    depth = min(4, image.width // 4, image.height // 4)
    edge_pairs = [
        (
            [image.getpixel((x, 0)) for x in range(image.width)],
            [image.getpixel((x, depth)) for x in range(image.width)],
        ),
        (
            [image.getpixel((x, image.height - 1)) for x in range(image.width)],
            [
                image.getpixel((x, image.height - 1 - depth))
                for x in range(image.width)
            ],
        ),
        (
            [image.getpixel((0, y)) for y in range(image.height)],
            [image.getpixel((depth, y)) for y in range(image.height)],
        ),
        (
            [image.getpixel((image.width - 1, y)) for y in range(image.height)],
            [
                image.getpixel((image.width - 1 - depth, y))
                for y in range(image.height)
            ],
        ),
    ]
    scores = []
    for edge, inner in edge_pairs:
        lightness = [sum(pixel[:3]) / 3 for pixel in edge]
        inner_lightness = [sum(pixel[:3]) / 3 for pixel in inner]
        edge_mean = sum(lightness) / len(lightness)
        inner_mean = sum(inner_lightness) / len(inner_lightness)
        near_white_fraction = sum(1 for pixel in edge if near_white(pixel)) / len(edge)
        # A separator is pale, uniform, and discontinuous from the nearby panel.
        # A pale painted background continues inward and should not be rejected.
        scores.append(
            near_white_fraction
            if edge_mean >= 252
            and pstdev(lightness) < 4
            and abs(edge_mean - inner_mean) >= 6
            else 0.0
        )
    return max(scores)


def main() -> None:
    args = parse_args()
    expressions = [item.strip() for item in args.expressions.split(",") if item.strip()]
    expected = args.columns * args.rows
    if len(expressions) != expected:
        raise SystemExit(f"Expected {expected} expressions, received {len(expressions)}")

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

    for index, expression in enumerate(expressions):
        row, column = divmod(index, args.columns)
        source_box = (
            x_spans[column][0],
            y_spans[row][0],
            x_spans[column][1],
            y_spans[row][1],
        )
        cell = center_square(
            sheet.crop(source_box), vertical_anchor=args.vertical_anchor
        )
        white_border = border_white_fraction(cell)
        cell = cell.resize((args.size, args.size), Image.Resampling.LANCZOS)

        filename = f"{args.name.lower()}-{expression}.png"
        destination = args.out_dir / filename
        if destination.exists() and not args.overwrite:
            raise SystemExit(
                f"Refusing to overwrite {destination}; use a staging directory "
                "or pass --overwrite"
            )
        cell.save(destination, optimize=True)
        manifest.append(
            {
                "file": filename,
                "expression": expression,
                "source_box": source_box,
                "size": [args.size, args.size],
                "source_border_white_fraction": round(white_border, 6),
            }
        )

    manifest_stem = args.name.lower()
    if args.sheet_id:
        manifest_stem += f"-{args.sheet_id}"
    manifest_path = args.out_dir / f"{manifest_stem}-manifest.json"
    if manifest_path.exists() and not args.overwrite:
        raise SystemExit(
            f"Refusing to overwrite {manifest_path}; use a staging directory "
            "or pass --overwrite"
        )
    manifest_path.write_text(
        json.dumps(
            {
                "name": args.name,
                "source": str(args.sheet),
                "grid": [args.columns, args.rows],
                "cropStrategy": "detected-white-gutters",
                "verticalAnchor": args.vertical_anchor,
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
