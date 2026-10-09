# XCI project workbench: update comparison, local AI, and raw HFS0 rebuilds

This is an **experimental metadata engineering tool**, not a decryptor and not
a game patcher or turnkey PC port. It does not modify original game images.

## 1. Inspect original XCI and locally exported game/update metadata

Use the existing standalone XCI scanner for partition metadata:

    python3 tools/xci_inventory.py "/path/to/your-owned-game.xci" \
      --output-dir "/path/to/analysis"

If you have the optional metadata-only JSON report from the Switch homebrew UI
(or any JSON with similar title/content fields), create a consolidated plan:

    python3 tools/xci_project.py project \
      --xci "/path/to/your-owned-game.xci" \
      --title-report "/path/to/switch-title-report.json" \
      --assets "/path/to/readable-assets" \
      --output "/path/to/analysis/project.json"

You can repeat --title-report to compare multiple offline observations.
**Only supplied numeric versions of the SAME title ID can be compared**.
The highest observed version is NOT necessarily the latest official update.
A gamecard XCI update partition commonly contains SYSTEM firmware data, not a
game update. The tool never guesses an update, release date or game version.

The reader retains only a restricted list of non-secret JSON fields, discards
keys/tickets/certificates, and does not send data to any service by default.
Encrypted files and unknown proprietary formats remain opaque.

## 2. Optional local Ollama analysis

With an Ollama server running locally, optionally add:

    --local-ai qwen3:8b

Only summarized nonsecret metadata (observed version numbers, asset file-type
counts, partition names, limitations) is sent to localhost 127.0.0.1:11434.
Raw ROM bytes, assets, image paths and keys are never sent by this tool.
If Ollama is unavailable, omit --local-ai and continue deterministically.
AI suggestions are NOT treated as proof that updates or game assets exist.

## 3. Rebuild raw, unencrypted HFS0 structures

Given your own flat directory of unencrypted, readable research files:

    python3 tools/xci_project.py pack-hfs0 \
      "/path/to/plain-files" \
      "/path/to/output/raw-archive.hfs0"

The packer constructs a real HFS0 header, file offset table, string table,
and SHA-256 hashed prefixes (default up to 512 bytes per file). It writes a
separate output file and never changes the originals. This is independently
testable using the existing HFS0 scanner.

**A raw HFS0 is NOT a valid or bootable XCI**. The tool does not regenerate
signed gamecard headers, encrypt Nintendo content, repack signed NCAs, bypass
content integrity, or produce a Windows/Linux executable from a Switch ROM.
Do not rename the output to .xci and expect it to run. Building a native PC
port requires legitimate access to implementation logic and usable assets.

## CI and next development steps

All tests use tiny synthetic, self-generated files: no Nintendo keys, games or
commercial content are used. Once both this tool and the local Codespace
firmware changes are pushed, separately test the Switch title exporter
schema and full NRO builds against hardware.

    python3 -m unittest discover -s tests -p 'test_xci_project.py' -v

Future work: provide a title-export schema sample (without keys), build
cross-release update maps using verified CNMT metadata, validate content
integrity, offer previews for supported open/unprotected asset formats, and
document rights-cleared porting workflows. Actual encrypted asset inspection
is NOT yet implemented.
