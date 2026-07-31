#!/usr/bin/env python3
"""Merge validated avatar packs into one canonical directory and manifest.

Two merge axes are supported. The character axis joins packs that cover
different people with the same expression vocabulary. The expression axis
joins packs that cover the same people with disjoint expression sets, which
is how a vocabulary expansion reaches an already-promoted pack.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("packs", nargs="+", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--axis", choices=("character", "expression"), default="character")
    parser.add_argument(
        "--expression-vocabulary",
        type=Path,
        help="Vocabulary defining the merged expression order. Required for --axis expression.",
    )
    return parser.parse_args()


def copy_output(pack: Path, out_dir: Path, filename: str, seen_files: set[str]) -> None:
    if filename in seen_files:
        raise SystemExit(f"Duplicate output filename: {filename}")
    seen_files.add(filename)

    source = pack / filename
    destination = out_dir / filename
    if source.resolve() != destination.resolve():
        if destination.exists():
            raise SystemExit(f"Refusing to overwrite: {destination}")
        shutil.copy2(source, destination)


def merge_on_characters(manifests, out_dir: Path, seen_files: set[str]) -> list[dict]:
    expression_counts = {manifest["expressionCount"] for _, manifest in manifests}
    vocabularies = {manifest["expressionVocabulary"] for _, manifest in manifests}
    if len(expression_counts) != 1 or len(vocabularies) != 1:
        raise SystemExit("Packs use incompatible expression vocabularies")

    characters = []
    seen_names: set[str] = set()
    for pack, manifest in manifests:
        for character in manifest["characters"]:
            name = character["name"]
            if name in seen_names:
                raise SystemExit(f"Duplicate character: {name}")
            seen_names.add(name)
            for output in character["outputs"]:
                copy_output(pack, out_dir, output["file"], seen_files)
            characters.append(character)
    return characters


def merge_on_expressions(
    manifests, out_dir: Path, seen_files: set[str], vocabulary_path: Path
) -> list[dict]:
    vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    states = vocabulary.get("states", vocabulary.get("expressions", []))
    order = {item["id"]: index for index, item in enumerate(states)}

    name_sets = [
        tuple(sorted(character["name"] for character in manifest["characters"]))
        for _, manifest in manifests
    ]
    if len(set(name_sets)) != 1:
        first = set(name_sets[0])
        for names, (pack, _) in zip(name_sets[1:], manifests[1:]):
            difference = first.symmetric_difference(names)
            if difference:
                raise SystemExit(
                    f"{pack}: character set differs from the first pack: {sorted(difference)}"
                )
    names = list(name_sets[0])

    merged: dict[str, dict] = {
        name: {"name": name, "outputs": [], "warnings": []} for name in names
    }
    seen_outputs: dict[str, set[tuple[str, str | None]]] = {
        name: set() for name in names
    }

    for pack, manifest in manifests:
        for character in manifest["characters"]:
            name = character["name"]
            for output in character["outputs"]:
                expression = output["expression"]
                variant = output.get("variant")
                output_key = (expression, variant)
                if expression not in order:
                    raise SystemExit(
                        f"{name}: expression {expression} is absent from {vocabulary_path}"
                    )
                if output_key in seen_outputs[name]:
                    raise SystemExit(
                        f"{name}: duplicate output across packs: {output_key}"
                    )
                seen_outputs[name].add(output_key)
                copy_output(pack, out_dir, output["file"], seen_files)
                merged[name]["outputs"].append(output)
            merged[name]["warnings"].extend(character.get("warnings", []))

    expression_counts = {
        len({output["expression"] for output in character["outputs"]})
        for character in merged.values()
    }
    if len(expression_counts) != 1:
        raise SystemExit(
            f"Merged characters have uneven expression counts: "
            f"{sorted(expression_counts)}"
        )

    for character in merged.values():
        character["outputs"].sort(
            key=lambda output: (
                order[output["expression"]],
                output.get("variant") is not None,
                output.get("variant", ""),
            )
        )
    return [merged[name] for name in names]


def main() -> None:
    args = parse_args()
    if args.axis == "expression" and args.expression_vocabulary is None:
        raise SystemExit("--axis expression requires --expression-vocabulary")

    manifests = []
    for pack in args.packs:
        manifest_path = pack / "pack-manifest.json"
        manifests.append(
            (pack.resolve(), json.loads(manifest_path.read_text(encoding="utf-8")))
        )

    sizes = {tuple(manifest["outputSize"]) for _, manifest in manifests}
    if len(sizes) != 1:
        raise SystemExit("Packs use incompatible dimensions")

    seen_files: set[str] = set()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.axis == "character":
        characters = merge_on_characters(manifests, args.out_dir, seen_files)
        vocabulary = manifests[0][1]["expressionVocabulary"]
    else:
        characters = merge_on_expressions(
            manifests, args.out_dir, seen_files, args.expression_vocabulary
        )
        vocabulary = str(args.expression_vocabulary.resolve())

    expression_count = len(
        {output["expression"] for output in characters[0]["outputs"]}
    )
    image_count = sum(len(character["outputs"]) for character in characters)
    report = {
        "schemaVersion": 1,
        "pipelineId": args.pipeline_id,
        "mergeAxis": args.axis,
        "sourcePacks": [
            {
                "pipelineId": manifest["pipelineId"],
                "manifest": str(pack / "pack-manifest.json"),
            }
            for pack, manifest in manifests
        ],
        "expressionVocabulary": vocabulary,
        "outputSize": list(sizes.pop()),
        "characterCount": len(characters),
        "expressionCount": expression_count,
        "imageCount": image_count,
        "characters": characters,
    }
    (args.out_dir / "pack-manifest.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Merged {report['imageCount']} images for "
        f"{report['characterCount']} characters into {args.out_dir}."
    )


if __name__ == "__main__":
    main()
