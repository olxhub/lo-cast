#!/usr/bin/env python3
"""Build and validate a normalized avatar pack from a declarative pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from crop_expression_sheet import border_white_fraction, center_square


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(base: Path, value: str) -> Path:
    return (base / value).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_override(source: Path, destination: Path, size: int) -> None:
    image = Image.open(source).convert("RGB")
    image = center_square(image)
    # Standalone generations can carry a one-pixel frame. Contract slightly.
    inset = max(1, round(image.width * 0.01))
    image = image.crop((inset, inset, image.width - inset, image.height - inset))
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    image.save(destination, optimize=True)


def main() -> None:
    args = parse_args()
    pipeline_path = args.pipeline.resolve()
    pipeline_dir = pipeline_path.parent
    pipeline = read_json(pipeline_path)

    vocabulary_path = resolve(pipeline_dir, pipeline["expressionVocabulary"])
    vocabulary = read_json(vocabulary_path)
    vocabulary_expression_ids = [
        item["id"] for item in vocabulary.get("states", vocabulary.get("expressions", []))
    ]
    expression_ids = pipeline.get("expressions", vocabulary_expression_ids)
    unknown_expression_ids = sorted(
        set(expression_ids) - set(vocabulary_expression_ids)
    )
    if unknown_expression_ids:
        raise SystemExit(
            f"Pipeline requests unknown expressions: {unknown_expression_ids}"
        )
    if len(expression_ids) != len(set(expression_ids)):
        raise SystemExit("Pipeline expression list contains duplicate IDs")
    expected = set(expression_ids)
    output_variants = pipeline.get("outputVariants", {})
    unknown_variant_expressions = sorted(set(output_variants) - expected)
    if unknown_variant_expressions:
        raise SystemExit(
            f"Pipeline defines variants for unknown expressions: "
            f"{unknown_variant_expressions}"
        )
    invalid_variants = sorted(
        variant
        for variant in output_variants.values()
        if not variant or not variant.replace("-", "").isalnum()
    )
    if invalid_variants:
        raise SystemExit(f"Pipeline contains invalid variant IDs: {invalid_variants}")

    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise SystemExit(
            f"Output directory must be absent or empty: {args.out_dir}. "
            "This prevents accidental replacement of a validated pack."
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)

    cropper = Path(__file__).with_name("crop_expression_sheet.py")
    character_reports = []

    for character in pipeline["characters"]:
        name = character["name"].lower()
        for sheet_index, sheet_spec in enumerate(character["sheets"], start=1):
            sheet_path = resolve(pipeline_dir, sheet_spec["path"])
            expressions = sheet_spec.get("expressions", expression_ids)
            command = [
                sys.executable,
                str(cropper),
                str(sheet_path),
                "--name",
                name,
                "--sheet-id",
                f"sheet-{sheet_index}",
                "--columns",
                str(sheet_spec.get("columns", 4)),
                "--rows",
                str(sheet_spec.get("rows", 6)),
                "--size",
                str(pipeline["outputSize"]),
                "--inset",
                str(pipeline["inset"]),
                "--gutter-threshold",
                str(pipeline["gutterThreshold"]),
                "--vertical-anchor",
                sheet_spec.get("verticalAnchor", "center"),
                "--expressions",
                ",".join(expressions),
                "--out-dir",
                str(args.out_dir),
            ]
            subprocess.run(command, check=True)

        canonical_cells = character.get("cells", character.get("overrides", {}))
        for expression, source_value in canonical_cells.items():
            if expression not in expected:
                raise SystemExit(f"{name}: unknown override expression {expression}")
            source = resolve(pipeline_dir, source_value)
            normalized_override(
                source,
                args.out_dir / f"{name}-{expression}.png",
                pipeline["outputSize"],
            )

        for expression, variant in output_variants.items():
            source = args.out_dir / f"{name}-{expression}.png"
            destination = args.out_dir / f"{name}-{expression}-{variant}.png"
            if destination.exists():
                raise SystemExit(f"Refusing to overwrite variant: {destination}")
            source.rename(destination)

        files = {}
        for expression in expression_ids:
            variant = output_variants.get(expression)
            suffix = f"-{variant}" if variant else ""
            files[expression] = args.out_dir / f"{name}-{expression}{suffix}.png"
        expected_paths = set(files.values())
        actual_paths = set(args.out_dir.glob(f"{name}-*.png"))
        missing = sorted(path.name for path in expected_paths - actual_paths)
        unexpected = sorted(path.name for path in actual_paths - expected_paths)
        if missing or unexpected:
            raise SystemExit(
                f"{name}: vocabulary mismatch; missing={missing}, "
                f"unexpected={unexpected}"
            )

        outputs = []
        warnings = []
        for expression in expression_ids:
            path = files[expression]
            with Image.open(path) as image:
                if image.size != (pipeline["outputSize"], pipeline["outputSize"]):
                    raise SystemExit(f"{path}: invalid dimensions {image.size}")
                separator_score = border_white_fraction(image.convert("RGB"))
                if separator_score > 0.65:
                    warnings.append(
                        {
                            "file": path.name,
                            "type": "pale-uniform-edge",
                            "score": round(separator_score, 6),
                        }
                    )
            output = {
                "expression": expression,
                "file": path.name,
                "sha256": sha256(path),
            }
            variant = output_variants.get(expression)
            if variant:
                output["variant"] = variant
            outputs.append(output)

        character_reports.append(
            {"name": name, "outputs": outputs, "warnings": warnings}
        )

    report = {
        "schemaVersion": 1,
        "pipelineId": pipeline["pipelineId"],
        "pipeline": str(pipeline_path),
        "expressionVocabulary": str(vocabulary_path),
        "outputSize": [pipeline["outputSize"], pipeline["outputSize"]],
        "characterCount": len(character_reports),
        "expressionCount": len(expression_ids),
        "imageCount": len(character_reports) * len(expression_ids),
        "characters": character_reports,
    }
    (args.out_dir / "pack-manifest.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Validated {report['imageCount']} images for "
        f"{report['characterCount']} characters at "
        f"{pipeline['outputSize']}x{pipeline['outputSize']}."
    )


if __name__ == "__main__":
    main()
