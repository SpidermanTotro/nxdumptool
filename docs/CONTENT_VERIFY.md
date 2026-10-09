# Offline content SHA-256 verification and DLC grouping

This tool complements the XCI HFS0 inventory and optional Switch metadata
export. It **hashes entire local files** (streaming 8 MiB blocks) and compares
each digest with an independent reference manifest you provide.

No keys or game data are uploaded; the script does not decrypt, modify,
download, patch or repack anything. It does not prove Nintendo authenticity
unless your reference hashes have themselves been independently authenticated.

## Reference-manifest format

Create a JSON file such as expected-hashes.json:

~~~json
{
  "schema": "nxdt-content-hashes-v1",
  "files": [
    {
      "path": "00000000000000000000000000000000.nca",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "size_bytes": 123456,
      "title_id": "0100000000000001",
      "content_type": "add_on_content"
    }
  ]
}
~~~

All digests and sizes above are **dummy examples**, not real game references.
Only use actual hashes from an independently trusted source when verifying
real data. If you don't have trusted hashes, compute an inventory instead;
a file's hash compared to itself cannot confirm integrity.

Run from the repository root:

    python3 tools/content_verify.py "/path/to/accessible-files" \
      --manifest "/path/to/expected-hashes.json" \
      --output "/path/to/results/verification.json"

Results include verified/mismatched/missing files and per-title counts,
including any DLC type labels already present in the supplied manifest.
The tool does not discover per-DLC metadata inside encrypted content by itself.

Exit status 0: all entries match. Exit 1: at least one mismatch or unknown.
Exit 2: invalid inputs, unsafe paths or output-write errors.

Source files are opened read-only, path traversal and symlinks are rejected,
and reports cannot be placed inside the source directory.

Tests use synthetic, rights-free file contents only:

    python3 -m unittest discover -s tests -p 'test_content_verify.py' -v

Remaining Switch-side work: push and review the Codespace's modified
23.0.1 source first; then connect the actual card-only DLC records and
verified metadata-export schema. The PC verifier does not replace that work.
