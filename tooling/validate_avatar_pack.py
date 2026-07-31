#!/usr/bin/env python3
"""Verify normalized avatar dimensions and hashes against a pack manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--manifest", default="pack-manifest.json")
    args = parser.parse_args()

    manifest_path = args.pack_dir / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_size = tuple(manifest["outputSize"])
    checked = 0
    seen_files: set[str] = set()
    expected_expression_count = manifest["expressionCount"]
    supported_expressions: set[str] = set()

    for character in manifest["characters"]:
        name = character["name"]
        seen_outputs: set[tuple[str, str | None]] = set()
        expressions: set[str] = set()
        for output in character["outputs"]:
            expression = output["expression"]
            variant = output.get("variant")
            output_key = (expression, variant)
            if output_key in seen_outputs:
                raise SystemExit(f"{name}: duplicate output {output_key}")
            seen_outputs.add(output_key)
            expressions.add(expression)
            supported_expressions.add(expression)

            expected_filename = f"{name}-{expression}"
            if variant:
                expected_filename += f"-{variant}"
            expected_filename += ".png"
            if output["file"] != expected_filename:
                raise SystemExit(
                    f"{name}: expected filename {expected_filename}, "
                    f"received {output['file']}"
                )
            if output["file"] in seen_files:
                raise SystemExit(f"Duplicate filename: {output['file']}")
            seen_files.add(output["file"])

            path = args.pack_dir / output["file"]
            if not path.is_file():
                raise SystemExit(f"Missing: {path}")
            with Image.open(path) as image:
                if image.size != expected_size:
                    raise SystemExit(
                        f"{path}: expected {expected_size}, received {image.size}"
                    )
            actual_hash = sha256(path)
            if actual_hash != output["sha256"]:
                raise SystemExit(f"{path}: SHA-256 mismatch")
            checked += 1

        if len(expressions) != expected_expression_count:
            raise SystemExit(
                f"{name}: expected {expected_expression_count} expressions; "
                f"received {len(expressions)}"
            )

    if checked != manifest["imageCount"]:
        raise SystemExit(
            f"Manifest expected {manifest['imageCount']} images; checked {checked}"
        )
    invalid_fallbacks = {
        source: target
        for source, target in manifest.get("stateFallbacks", {}).items()
        if source in supported_expressions or target not in supported_expressions
    }
    if invalid_fallbacks:
        raise SystemExit(f"Invalid state fallbacks: {invalid_fallbacks}")
    actual_files = {path.name for path in args.pack_dir.glob("*.png")}
    unexpected_files = sorted(actual_files - seen_files)
    missing_files = sorted(seen_files - actual_files)
    if unexpected_files or missing_files:
        raise SystemExit(
            f"Directory mismatch: unexpected={unexpected_files[:5]}, "
            f"missing={missing_files[:5]}"
        )
    print(f"Verified {checked} images against {manifest_path}.")


if __name__ == "__main__":
    main()
