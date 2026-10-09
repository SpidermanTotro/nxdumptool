#!/usr/bin/env python3
"""Offline, read-only XCI/HFS0 metadata inventory. Never decrypts or extracts assets."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from datetime import date
from pathlib import Path

ROOT = 0x10000
HEADER = 0x1000
MAX_FILES = 4096
MAX_STRINGS = 4 * 1024 * 1024
MAX_PREFIX = 1024 * 1024
PARTITIONS = {"secure", "normal", "update", "logo"}

class InvalidImage(ValueError):
    pass

def read_at(stream, pos: int, count: int, end: int) -> bytes:
    if pos < 0 or count < 0 or pos + count > end:
        raise InvalidImage(f"out-of-bounds read: offset 0x{pos:X}")
    stream.seek(pos)
    chunk = stream.read(count)
    if len(chunk) != count:
        raise InvalidImage(f"truncated input at 0x{pos:X}")
    return chunk

def hfs0(stream, start: int, end: int) -> dict:
    magic, files, text_size, _ = struct.unpack("<4sIII", read_at(stream, start, 16, end))
    if magic != b"HFS0":
        raise InvalidImage(f"expected HFS0 at 0x{start:X}")
    if files > MAX_FILES or text_size > MAX_STRINGS:
        raise InvalidImage("oversized HFS0 directory table")
    header_len = 16 + files * 0x40 + text_size
    if start + header_len > end:
        raise InvalidImage("HFS0 header overflows its partition")
    raw = read_at(stream, start + 16, files * 0x40 + text_size, end)
    names = raw[files * 0x40:]
    data_start = start + header_len
    entries = []
    for index in range(files):
        entry = raw[index * 0x40:(index + 1) * 0x40]
        offset, length, name_pos, hashed = struct.unpack_from("<QQII", entry, 0)
        if name_pos >= len(names):
            raise InvalidImage(f"filename index outside table: {index}")
        end_pos = names.find(b"\0", name_pos)
        if end_pos == -1:
            raise InvalidImage(f"missing filename terminator: {index}")
        filename = names[name_pos:end_pos].decode("utf-8", "replace")
        absolute = data_start + offset
        if absolute < data_start or absolute + length > end:
            raise InvalidImage(f"file outside partition: {index}")
        if hashed > length:
            raise InvalidImage(f"hash length exceeds file length: {index}")
        check = "not_applicable"
        if hashed:
            if hashed > MAX_PREFIX:
                check = "skipped_over_size_limit"
            else:
                actual = hashlib.sha256(read_at(stream, absolute, hashed, end)).digest()
                check = "match" if actual == entry[0x20:0x40] else "mismatch"
        entries.append({
            "name": filename, "offset": absolute, "size_bytes": length,
            "hashed_prefix_bytes": hashed, "hashed_prefix_sha256": check,
            "type": "metadata_nca" if filename.lower().endswith(".cnmt.nca")
                    else "nca" if filename.lower().endswith(".nca") else "other",
        })
    return {"offset": start, "header_bytes": header_len,
            "file_count": files, "entries": entries}

def analyze(path: Path, *, release_date: date | None = None,
            as_of: date | None = None) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise InvalidImage("input must be a local file")
    file_size = path.stat().st_size
    if file_size < ROOT + 16:
        raise InvalidImage("too small for XCI header and HFS0 root")
    with path.open("rb") as stream:
        header = read_at(stream, HEADER, 0x200, file_size)
        if header[0x100:0x104] != b"HEAD":
            raise InvalidImage("missing HEAD gamecard magic")
        root = hfs0(stream, ROOT, file_size)
        declared_offset, declared_size = struct.unpack_from("<QQ", header, 0x130)
        root_digest = "not_verified"
        if declared_offset == ROOT and 16 <= declared_size <= MAX_PREFIX and ROOT + declared_size <= file_size:
            digest = hashlib.sha256(read_at(stream, ROOT, declared_size, file_size)).digest()
            root_digest = "match" if digest == header[0x140:0x160] else "mismatch"
        elif declared_offset != ROOT:
            root_digest = "unsupported_header_offset"
        partitions = []
        for item in root["entries"]:
            if item["name"].lower() not in PARTITIONS:
                continue
            try:
                section = hfs0(stream, item["offset"], item["offset"] + item["size_bytes"])
                section["name"] = item["name"]
                partitions.append(section)
            except InvalidImage as exc:
                partitions.append({"name": item["name"], "status": "unreadable", "reason": str(exc)})
    today = as_of or date.today()
    categories = ("textures", "models_and_objects", "characters",
                  "plants_and_terrain", "audio", "scripts_and_behavior")
    return {
        "schema": "nxdt-xci-inventory-v1",
        "source": {"filename": path.name, "size_bytes": file_size, "read_only": True},
        "root_header_sha256": root_digest, "root": root, "partitions": partitions,
        "release_date": release_date.isoformat() if release_date else None,
        "release_date_source": "user_supplied" if release_date else "unknown",
        "age_days_as_of": (today - release_date).days if release_date else None,
        "as_of": today.isoformat(),
        "game_update_version": "unknown_without_verified_content_metadata",
        "required_firmware": "unknown_without_verified_content_metadata",
        "update_partition_warning": "The XCI update partition generally carries system firmware, not necessarily a game patch.",
        "modernization_inventory": {
            name: {"status": "not_inspected", "next_step": "Review rights-cleared source assets, formats and performance budgets."}
            for name in categories
        },
        "pc_port": {"status": "not_automatic",
                    "next_step": "Requires legal access to source or permitted reimplementation, engine/runtime work and rights-cleared assets."},
        "verification_scope": "Only HFS0 headers and hashed file prefixes are checked; no NCA signatures, content decryption, full-image hashes or asset examination.",
    }

def make_markdown(doc: dict) -> str:
    src = doc["source"]
    lines = [
        "# XCI read-only inventory", "",
        "Image: " + src["filename"],
        "Image size: " + f"{src['size_bytes']:,}" + " bytes",
        "Root HFS0 header SHA-256: " + doc["root_header_sha256"],
        "Release date: " + (doc["release_date"] or "unknown") + " (" + doc["release_date_source"] + ")",
        "Age (days): " + (str(doc["age_days_as_of"]) if doc["age_days_as_of"] is not None else "unknown"),
        "Game update version: unknown",
        "Required firmware: unknown", "",
        "## Partition and file metadata", "",
    ]
    for section in [doc["root"]] + doc["partitions"]:
        lines.append("### " + section.get("name", "root").replace("#", ""))
        if "entries" not in section:
            lines.append("Unable to read: " + section.get("reason", "unknown"))
        else:
            lines.extend(("| Filename | Bytes | Prefix SHA-256 |",
                          "| --- | ---: | --- |"))
            for item in section["entries"]:
                name = item["name"].replace("|", "/").replace("\n", " ").replace("\r", " ")
                lines.append(f"| {name} | {item['size_bytes']:,} | {item['hashed_prefix_sha256']} |")
        lines.append("")
    lines += ["## Modernization investigation (NOT an asset scan)", ""]
    for key in doc["modernization_inventory"]:
        lines.append("- " + key.replace("_", " ").title() + ": not inspected")
    lines += ["", "## Limitations", "",
              "- " + doc["update_partition_warning"],
              "- " + doc["verification_scope"],
              "- " + doc["pc_port"]["next_step"],
              "- No files, game assets or textures were extracted, downloaded or patched."]
    return "\n".join(lines) + "\n"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xci", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("xci-reports"))
    parser.add_argument("--release-date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--as-of", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--format", choices=["both", "json", "md"], default="both")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        doc = analyze(args.xci, release_date=args.release_date, as_of=args.as_of)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", args.xci.stem)[:100] or "image"
        candidates = [
            ("json", args.output_dir / (stem + ".inventory.json"), json.dumps(doc, indent=2) + "\n"),
            ("md", args.output_dir / (stem + ".inventory.md"), make_markdown(doc)),
        ]
        for kind, path, content in candidates:
            if args.format not in ("both", kind):
                continue
            with path.open("w" if args.overwrite else "x", encoding="utf-8") as stream:
                stream.write(content)
            print(path)
    except (InvalidImage, OSError) as exc:
        parser.exit(2, f"XCI scan failed: {exc}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
