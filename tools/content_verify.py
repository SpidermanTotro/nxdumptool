#!/usr/bin/env python3
"""Read-only, full-file SHA-256 verification of locally accessible content.

No decryption, Nintendo keys, network connections or game modifications.
Expected hashes MUST come from an independent, user-supplied trusted manifest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 20000
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
TITLE16 = re.compile(r"^(?:0x)?[0-9a-fA-F]{16}$")


class ManifestError(ValueError):
    pass


def load_manifest(path: Path) -> list[dict]:
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest not found or exceeds 4 MiB")
    with path.open("r", encoding="utf-8") as stream:
        obj = json.load(stream)
    if not isinstance(obj, dict) or obj.get("schema") != "nxdt-content-hashes-v1":
        raise ManifestError("expected schema nxdt-content-hashes-v1")
    records = obj.get("files")
    if not isinstance(records, list) or len(records) > MAX_ENTRIES:
        raise ManifestError("files must be a list containing at most 20000 entries")
    seen = set()
    validated = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise ManifestError(f"files[{i}] is not an object")
        allowed = {"path", "sha256", "size_bytes", "title_id", "content_type"}
        if not set(record).issubset(allowed):
            raise ManifestError(f"files[{i}] contains unknown fields")
        raw = record.get("path")
        digest = record.get("sha256")
        if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
            raise ManifestError(f"files[{i}] has invalid path")
        name = PurePosixPath(raw)
        if name.is_absolute() or raw.startswith("./") or any(p in (".", "..", "") for p in raw.split("/")):
            raise ManifestError(f"files[{i}] has unsafe relative path")
        if raw in seen:
            raise ManifestError(f"duplicate file path: {raw}")
        seen.add(raw)
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ManifestError(f"files[{i}] has invalid SHA-256")
        size = record.get("size_bytes")
        if size is not None and (type(size) is not int or size < 0):
            raise ManifestError(f"files[{i}] has invalid size")
        title_id = record.get("title_id")
        if title_id is not None and (not isinstance(title_id, str) or not TITLE16.fullmatch(title_id)):
            raise ManifestError(f"files[{i}] has invalid title_id")
        content_type = record.get("content_type")
        if content_type is not None and (not isinstance(content_type, str) or len(content_type) > 64
                                         or not re.fullmatch(r"[A-Za-z0-9_ -]+", content_type)):
            raise ManifestError(f"files[{i}] has invalid content_type")
        validated.append({
            "path": raw, "sha256": digest.lower(), "size_bytes": size,
            "title_id": title_id.lower().removeprefix("0x") if title_id else None,
            "content_type": content_type if content_type else "unknown",
        })
    return validated


def _open_safe_file(root: Path, relative: str):
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise ManifestError("symlink path is not allowed")
    if not path.is_file():
        raise FileNotFoundError(relative)
    if not path.resolve().is_relative_to(root):
        raise ManifestError("content path escapes input directory")
    return path


def verify(directory: Path, entries: list[dict]) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise ManifestError("content directory must be a normal folder")
    root = directory.resolve(strict=True)
    results = []
    summary: dict[str, int] = defaultdict(int)
    by_title: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in entries:
        relative = record["path"]
        result = {
            "path": relative,
            "title_id": record["title_id"],
            "content_type": record["content_type"],
            "reference_sha256": record["sha256"],
            "reference_size_bytes": record["size_bytes"],
        }
        try:
            path = _open_safe_file(root, relative)
            reported_size = path.stat().st_size
            result["actual_size_bytes"] = reported_size
            if record["size_bytes"] is not None and reported_size != record["size_bytes"]:
                result["status"] = "size_mismatch"
            else:
                sha = hashlib.sha256()
                with path.open("rb") as stream:
                    while data := stream.read(8 * 1024 * 1024):
                        sha.update(data)
                result["actual_sha256"] = sha.hexdigest()
                result["status"] = "match" if result["actual_sha256"] == record["sha256"] else "hash_mismatch"
        except (FileNotFoundError, PermissionError, IsADirectoryError):
            result["status"] = "missing_or_unreadable"
        except ManifestError:
            result["status"] = "unsafe_symlink_or_path"
        summary[result["status"]] += 1
        if record["title_id"]:
            by_title[record["title_id"]][result["status"]] += 1
        results.append(result)
    return {
        "schema": "nxdt-content-verification-v1",
        "source_directory": str(root),
        "verification_scope": "entire local file compared with caller-provided independent SHA-256",
        "trust_warning": "A hash match proves equality to the supplied digest only, not authenticity or Nintendo signature validity.",
        "game_update_warning": "Content-type and title-ID labels come from the supplied manifest; no online update check is performed.",
        "counts": dict(summary),
        "by_title": {k: dict(v) for k, v in sorted(by_title.items())},
        "files": results,
        "all_matched": bool(entries) and all(x["status"] == "match" for x in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="folder with your locally accessible files")
    parser.add_argument("--manifest", type=Path, required=True, help="trusted manifest JSON; see documentation")
    parser.add_argument("--output", type=Path, required=True, help="new report JSON path outside content folder")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing report")
    args = parser.parse_args()
    try:
        root = args.directory.resolve()
        target = args.output.resolve()
        if target == root or root in target.parents:
            raise ManifestError("output report must be outside the content directory")
        expected = load_manifest(args.manifest)
        result = verify(args.directory, expected)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w" if args.overwrite else "x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print(f"Verified {len(expected)} local files: {result['counts']}; report: {target}")
        return 0 if result["all_matched"] else 1
    except (ManifestError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Content verifier failed: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
