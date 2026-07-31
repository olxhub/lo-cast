#!/usr/bin/env python3
"""Build a file://-compatible JavaScript catalog for the static viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identities", type=Path, default=Path("catalog/identities.json"))
    parser.add_argument("--identity-set", type=Path, default=Path("catalog/identity-sets/complete-v1.json"))
    parser.add_argument("--states", type=Path, default=Path("catalog/states.json"))
    parser.add_argument("--state-set", type=Path, default=Path("catalog/state-sets/complete-v3.json"))
    parser.add_argument("--manifest", type=Path, default=Path("avatars/manifest.json"))
    parser.add_argument("--out", type=Path, default=Path("viewer/catalog.js"))
    args = parser.parse_args()

    identity_catalog = read_json(args.identities)
    identity_set = read_json(args.identity_set)
    state_catalog = read_json(args.states)
    state_set = read_json(args.state_set)
    manifest = read_json(args.manifest)

    identities_by_id = {item["id"]: item for item in identity_catalog["identities"]}
    states_by_id = {item["id"]: item for item in state_catalog["states"]}
    identity_ids = identity_set["identities"]
    state_ids = state_set["states"]

    missing_identities = [item for item in identity_ids if item not in identities_by_id]
    missing_states = [item for item in state_ids if item not in states_by_id]
    if missing_identities or missing_states:
        raise SystemExit(
            f"Catalog mismatch: identities={missing_identities}, states={missing_states}"
        )

    state_fallbacks = manifest.get("stateFallbacks", {})
    invalid_fallbacks = {
        source: target
        for source, target in state_fallbacks.items()
        if target not in states_by_id
    }
    if invalid_fallbacks:
        raise SystemExit(f"Invalid state fallbacks: {invalid_fallbacks}")

    expected_files = {
        f"{identity_id}-{state_id}.png"
        for identity_id in identity_ids
        for state_id in state_ids
    }
    manifest_outputs = [
        (character["name"], output)
        for character in manifest["characters"]
        for output in character["outputs"]
    ]
    manifest_files = {output["file"] for _, output in manifest_outputs}
    missing_files = sorted(expected_files - manifest_files)
    unknown_outputs = sorted(
        output["file"]
        for identity_id, output in manifest_outputs
        if identity_id not in identities_by_id or output["expression"] not in states_by_id
    )
    if missing_files or unknown_outputs:
        raise SystemExit(
            f"Manifest mismatch: missing={missing_files[:5]}, "
            f"unknown={unknown_outputs[:5]}"
        )

    payload = {
        "schemaVersion": 2,
        "libraryId": manifest["libraryId"],
        "filenamePattern": manifest["filenamePattern"],
        "outputSize": manifest["outputSize"],
        "stateFallbacks": state_fallbacks,
        "identities": [
            {
                "id": identities_by_id[item]["id"],
                "name": identities_by_id[item]["name"],
            }
            for item in identity_ids
        ],
        "states": [
            {
                key: states_by_id[item][key]
                for key in ("id", "kind", "description")
                if key in states_by_id[item]
            }
            for item in state_ids
        ],
        "images": [
            {
                key: value
                for key, value in {
                    "identity": identity_id,
                    "state": output["expression"],
                    "variant": output.get("variant"),
                    "file": output["file"],
                }.items()
                if value is not None
            }
            for identity_id, output in manifest_outputs
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "window.AVATAR_CATALOG = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {args.out} with {len(identity_ids)} identities and "
        f"{len(state_ids)} states and {len(manifest_outputs)} images."
    )


if __name__ == "__main__":
    main()
