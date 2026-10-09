# Read-only XCI game inventory (research prototype)

This command scans **unencrypted XCI/HFS0 file and partition tables only**.
It never decrypts an NCA, extracts textures, models, people, plants, or game code,
downloads updates, writes to the XCI, or produces an executable PC port.

## Usage

From the repository root (Python 3.10+; no third-party packages):

    python3 tools/xci_inventory.py "/path/to/my-game.xci" --output-dir "./reports"

Optional user-provided release date and fixed reference date:

    python3 tools/xci_inventory.py "/path/to/my-game.xci" \
      --release-date 2017-03-03 --as-of 2026-10-09 \
      --output-dir "./reports" --overwrite

Generated files:
- GAME.inventory.json: machine-readable HFS0 structure, partition names, sizes,
  bounded hashed-prefix SHA-256 comparisons, provenance and limitation fields.
- GAME.inventory.md: readable file inventory, provenance and category-specific
  modernization investigation checklist.

**Never infer a game release date from an XCI timestamp or claim a version is
current without a verified source.** The user-provided date is explicitly
labelled; absent a date, age is unknown. The XCI "update" partition usually
contains **system firmware**, not necessarily a title/game patch. Names of
encrypted NCA files don't reveal texture or model contents.

## PC modernization checklist

The generated report includes these *unexamined* categories as planning prompts:
textures, models/objects, characters, plants/terrain, audio, scripts/behavior.
For rights-cleared source assets, an actual asset pipeline would then need to
inspect formats, dimensions, performance budgets, fidelity, licensing,
compatibility with the destination game engine and platform testing.

A native PC port requires a legal source/reimplementation basis and
platform-specific development. The scanner does **not** emulate or port
Nintendo Switch games.

## Verification and privacy

- Input is opened read-only.
- HFS0 table lengths/offsets, filenames and partition bounds are validated.
- Only HFS0-prefix hash regions up to 1 MiB each are checked; whole NCA/XCI
  integrity, decryption and Nintendo signatures are explicitly out of scope.
- No keys, certificates, network transfers or commercial game data are
  included in reports.
- Reports are never overwritten unless --overwrite is requested.
- No console or firmware required for synthetic tests:

    python3 -m unittest discover -s tests -p 'test_xci_inventory.py' -v
