# LO Blocks Scenario Avatar Library

This repository is the avatar subsystem for
[`lo-blocks`](https://github.com/olxhub/lo-blocks/). Its corresponding source
code is published as [`olxhub/lo-cast`](https://github.com/olxhub/lo-cast/).
`lo-blocks` is part of
[Learning Observer](https://github.com/ArgLab/writing_observer/). This
repository contains semi-photographic avatars for scenario-based learning and
assessment. The published library currently covers 36 identities and 55
observable states, for 2,160 square 512×512 PNGs—including alternate
takes—intended to be displayed at smaller sizes.

## Repository history

Unlike most Learning Observer repositories, this repository does not treat Git
history as a permanent canonical record. Large generated binary assets are
corrected and replaced in place, and published history may be rewritten to
avoid retaining obsolete copies of those assets indefinitely. The current
tree and `avatars/manifest.json` are canonical; old commit IDs are not.

Consumers should use releases or the current default branch rather than pinning
unreleased commit IDs. Contributors with existing clones or forks may need to
rebase or fetch a fresh copy after a history rewrite.

## Library

`avatars/` is the distributable asset directory. Every image has a globally
unique filename using the stable convention:

```text
{identity}-{state}.png
{identity}-{state}-{variant}.png
```

For example, `aaliyah-calm.png`, `aaliyah-thinking.png`, and
`aaliyah-smile-alt.png` can be copied or served without relying on their parent
directory for identification. Alternate takes preserve the same semantic state
while providing visual variety; `alt` is a variant, not a separate expression.
`avatars/manifest.json` records the complete matrix, dimensions, filenames,
and SHA-256 hashes.

Renderer-specific state names can resolve through the manifest's
`stateFallbacks` map. For example, legacy `angryWithFang` requests resolve to
the library's first-class `snarling` state.

## Catalog

Identity and state are independent axes:

- `catalog/identities.json` defines each person.
- `catalog/identity-sets/` defines reusable selections of people. The Memphis
  set represents the University of Memphis context; other sets can be added
  without changing the state catalog.
- `catalog/states.json` defines facial expressions, gestures, props, and
  observable activity states.
- `catalog/state-sets/` provides useful state selections without making those
  selections part of the directory hierarchy.

The `complete-v1` state set preserves the original 36-state selection.
`complete-v2` preserves the earlier 43-state library, while `complete-v3`
describes the currently published 55-state library. The preview
orders semantic states alphabetically. Person view places alternate takes
immediately after their base image; state view shows one canonical take per
identity.

## Generation

`generation/recipes/` records sheet geometry, state order, crop settings, and
canonical single-cell sources. Page composition is retained deliberately: the
states generated together, and their order on a page, can affect consistency,
contrast, gesture carryover, and the interpretation of subtle expressions.

`generation/prompts/` contains the corresponding generation instructions.
High-resolution source sheets and identity anchors live locally under
`generation/sources/` and are excluded from the distributable repository.

To rebuild a recipe into a new directory:

```bash
python tooling/process_avatar_pack.py \
  generation/recipes/core-v1.json \
  --out-dir /tmp/faces-core
```

To verify the published library:

```bash
python tooling/validate_avatar_pack.py avatars --manifest manifest.json
```

The tools require Python 3 and Pillow.

## Viewer

Browse the [published avatar library](https://olxhub.github.io/lo-cast/viewer/),
or open `index.html` directly with a `file://` URL. The viewer supports person
and state views with shareable query parameters. It uses a generated classic
JavaScript catalog instead of `fetch()`, so it does not require a local web
server.

Regenerate its catalog after changing identities, states, or the published
manifest:

```bash
python tooling/build_viewer_catalog.py
```

`.github/workflows/pages.yml` deploys the same viewer and avatar paths to
GitHub Pages. Enable GitHub Actions as the Pages source in the repository
settings after pushing the repository.

## Application integration

The flat, unique filenames are intended to work with content systems that may
copy, mount, or serve assets under different directory layouts. A cast member
can resolve an observable state to `{identity}-{state}.png`; directory layout
is an implementation detail rather than part of the avatar identity.

## License and legal notice

This avatar subsystem is part of `lo-blocks` and is distributed under the GNU
Affero General Public License, version 3, with the additional terms in
`NOTICE.TXT`. See `LICENSE.TXT` and `NOTICE.TXT` for the complete terms.

lo-blocks is free and open-source software by
[Piotr Mitros](http://mitros.org/p).
[Project Repository](https://github.com/olxhub/lo-blocks/).
[Licensing information](http://mitros.org/p/lo/license.html).
Copyright © 2011-2026 Piotr Mitros and
[others](http://mitros.org/p/lo/contributors.html). Any representation of
another party as the original author or inventor of this tool or methodology is
a misrepresentation of origin and authorship. Source code for this avatar
subsystem: [`olxhub/lo-cast`](https://github.com/olxhub/lo-cast/). `lo-blocks`
is part of [Learning Observer](https://github.com/ArgLab/writing_observer/).
