#!/usr/bin/env python3
"""Read-only XCI analysis, title-update reconciliation, optional local AI, and plain HFS0 rebuilds.

A rebuilt HFS0 is *not* a valid or signed Switch XCI, game patch, or PC port.
No encrypted content is decrypted or modified. Standard-library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path

MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_HFS_ENTRIES = 4096
MAX_HFS_NAME_BYTES = 4 * 1024 * 1024
MAX_AI_BYTES = 12000
AI_ENDPOINT = "http://127.0.0.1:11434/api/generate"
SAFE_FIELDS = {
    "title_id", "application_id", "title_name", "title_type", "type",
    "version", "display_version", "firmware_version", "hos_version",
    "content_id", "content_type", "content_size", "size_bytes",
    "size", "id_offset", "status", "verified", "verification_status",
    "source", "filename",
}
DANGEROUS_FRAGMENTS = ("key", "ticket", "cert", "secret", "seed", "password", "token", "license")


def read_json(path: Path):
    if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("metadata report missing or exceeds 8 MiB")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def safe_records(value, *, limit: int = 10000) -> list[dict]:
    """Retain an allowlist of non-secret fields from arbitrary nested export JSON."""
    found: list[dict] = []
    queue = [value]
    nodes = 0
    while queue:
        part = queue.pop()
        nodes += 1
        if nodes > limit:
            raise ValueError("metadata report too deeply nested or large")
        if isinstance(part, list):
            queue.extend(reversed(part))
        elif isinstance(part, dict):
            item = {}
            for key, val in part.items():
                label = str(key).lower()
                if any(word in label for word in DANGEROUS_FRAGMENTS):
                    continue
                if label in SAFE_FIELDS and isinstance(val, (str, int, float, bool)):
                    item[label] = val
                if isinstance(val, (list, dict)):
                    queue.append(val)
            if item and any(k in item for k in ("title_id", "application_id", "content_id", "version")):
                found.append(item)
    return found


def _as_version(record: dict):
    value = record.get("version")
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xffffffff:
        return value
    if isinstance(value, str) and value.isdecimal() and len(value) < 11:
        return int(value)
    return None


def version_comparison(records: list[dict]) -> list[dict]:
    """Only compare numeric title versions for matching title IDs; no online claims."""
    by_title: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        title_id = rec.get("title_id") or rec.get("application_id")
        version = _as_version(rec)
        if isinstance(title_id, str) and re.fullmatch(r"(?:0x)?[0-9a-fA-F]{16}", title_id) and version is not None:
            by_title[title_id.lower().removeprefix("0x")].append(rec)
    result = []
    for title_id in sorted(by_title):
        entries = by_title[title_id]
        versions = sorted({_as_version(x) for x in entries})
        if not versions:
            continue
        result.append({
            "title_id": title_id,
            "observed_numeric_versions": versions,
            "highest_observed_version": versions[-1],
            "highest_version_scope": "only_supplied_local_metadata",
            "latest_available_online": "unknown",
            "source_count": len(entries),
        })
    return result


def build_project(xci: Path | None, title_reports: list[Path], assets: Path | None) -> dict:
    if __package__:
        from . import xci_inventory, asset_workbench
    else:
        import xci_inventory
        import asset_workbench

    doc = {
        "schema": "nxdt-xci-rebuild-workbench-v1",
        "mode": "inventory_and_rebuild_planning",
        "xci": None, "title_reports": [], "asset_inventory": None,
        "version_comparison": [], "warnings": [],
        "next_steps": [
            "Verify gamecard HFS0 partition structure and hashed prefixes.",
            "Compare locally observed signed content metadata and game update version records.",
            "Inspect accessible assets with format-specific tools; encrypted NCA content is opaque.",
            "Plan changes against legitimately available source assets and preserve originals.",
            "A valid playable modified XCI needs correct content integrity and encryption; this tool does not produce one.",
            "Native PC port requires engine/runtime work and rights-cleared source or permitted reimplementation.",
        ],
    }
    if xci:
        scanned = xci_inventory.analyze(xci)
        doc["xci"] = {
            "source_filename": scanned["source"]["filename"],
            "size_bytes": scanned["source"]["size_bytes"],
            "root_header_sha256": scanned["root_header_sha256"],
            "root_entries": scanned["root"]["entries"],
            "partitions": scanned["partitions"],
            "game_update_version": "unknown_without_verified_metadata",
            "firmware_version": "unknown_without_verified_metadata",
        }
        doc["warnings"].append(
            "An XCI 'update' partition ordinarily contains system firmware, not necessarily a game update."
        )
    flattened = []
    for path in title_reports:
        records = safe_records(read_json(path))
        doc["title_reports"].append({
            "filename": path.name,
            "metadata_record_count": len(records),
            "records": records,
        })
        flattened.extend(records)
        if not records:
            doc["warnings"].append(f"No recognized title/content fields found in {path.name}; schema adapter may be needed.")
    doc["version_comparison"] = version_comparison(flattened)
    if assets:
        inventory = asset_workbench.scan(assets, include_hashes=False)
        doc["asset_inventory"] = {
            "file_counts": inventory["file_counts"],
            "files": inventory["files"],
            "labels_are_filename_guesses": True,
        }
    if not title_reports:
        doc["warnings"].append("No verified title/update record exports supplied: game/update versions remain unknown.")
    doc["warnings"].append("Metadata analysis cannot identify encrypted textures, characters, plants or scripts.")
    return doc


def ask_local_ai(project: dict, model: str, *, timeout: int = 45) -> str:
    """Explicit opt-in: only sanitized summary metadata sent to localhost Ollama."""
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model):
        raise ValueError("invalid local model identifier")
    summary = {
        "observed_versions": project["version_comparison"][:70],
        "asset_type_counts": (project["asset_inventory"] or {}).get("file_counts", {}),
        "xci_partition_names": [
            x.get("name") for x in (project["xci"] or {}).get("partitions", [])
        ],
        "warnings": project["warnings"],
        "next_steps": project["next_steps"],
    }
    prompt = (
        "You are an offline game-metadata engineering reviewer. The attached data "
        "contains filenames and version metadata, not decrypted gameplay assets. "
        "Explain only grounded evidence, uncertainty, and actionable engineering work. "
        "Never claim to have seen encrypted textures, NPCs or patches. Do not claim "
        "the highest observed numeric version is the current official update. "
        "A valid PC port is not automatically produced. Do not request copyrighted "
        "data, firmware keys, secrets, or proprietary game packages.\n\n"
        + json.dumps(summary, ensure_ascii=False)[:MAX_AI_BYTES]
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = urllib.request.Request(
        AI_ENDPOINT, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(512_000)
    result = json.loads(body)
    if not isinstance(result, dict) or not isinstance(result.get("response"), str):
        raise ValueError("unexpected Ollama response")
    return result["response"]


def _files_in_one_folder(directory: Path, destination: Path):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("input must be a normal directory")
    directory = directory.resolve(strict=True)
    destination = destination.resolve()
    if destination == directory or directory in destination.parents:
        raise ValueError("output must be outside the input directory")
    paths = sorted(directory.iterdir(), key=lambda p: p.name)
    if len(paths) > MAX_HFS_ENTRIES:
        raise ValueError("too many HFS0 entries")
    for p in paths:
        if p.is_symlink() or not p.is_file() or "/" in p.name or "\x00" in p.name:
            raise ValueError(f"expected only regular, non-symlink files: {p.name}")
    return paths


def pack_plain_hfs0(source: Path, output: Path, *, overwrite: bool = False,
                    prefix_length: int = 0x200) -> dict:
    """Pack a plain HFS0 table from ordinary files, preserving content bytes.

    This never creates XCI signatures, encrypts NCAs, signs firmware, or builds
    a valid gamecard. It is for binary-format research/testing.
    """
    if not (0 <= prefix_length <= 1024 * 1024):
        raise ValueError("prefix length must be between 0 and 1048576")
    files = _files_in_one_folder(source, output)
    string_table = b""
    entries = []
    data_start = 0
    for f in files:
        name = f.name.encode("utf-8")
        if len(string_table) + len(name) + 1 > MAX_HFS_NAME_BYTES:
            raise ValueError("HFS0 name table too large")
        name_offset = len(string_table)
        string_table += name + b"\0"
        size = f.stat().st_size
        hashed = min(size, prefix_length)
        with f.open("rb") as readfile:
            digest = hashlib.sha256(readfile.read(hashed)).digest() if hashed else b"\0" * 32
        entries.append((f, data_start, size, name_offset, hashed, digest))
        data_start += size
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} exists: use --overwrite")
    fd, tmpname = tempfile.mkstemp(prefix=".nxdt-hfs0-", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(struct.pack("<4sIII", b"HFS0", len(files), len(string_table), 0))
            for f, offset, size, name_offset, hashed, digest in entries:
                out.write(struct.pack("<QQII8s32s", offset, size, name_offset, hashed, b"\0" * 8, digest))
            out.write(string_table)
            for f, *_ in entries:
                with f.open("rb") as inp:
                    while chunk := inp.read(1024 * 1024):
                        out.write(chunk)
        if output.exists() and not overwrite:
            raise FileExistsError(f"{output} exists: use --overwrite")
        os.replace(tmpname, output)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)
    return {
        "output": str(output), "size_bytes": output.stat().st_size,
        "format": "plain_unsigned_hfs0_not_xci",
        "file_count": len(files), "hashed_prefix_max_bytes": prefix_length,
        "xci_rebuilt": False, "source_files_unchanged": True,
    }


def write_report(path: Path, result: dict, *, overwrite: bool):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("project", help="join XCI, title-update and asset metadata into a rebuild plan")
    project.add_argument("--xci", type=Path)
    project.add_argument("--title-report", action="append", type=Path, default=[])
    project.add_argument("--assets", type=Path)
    project.add_argument("--output", type=Path, required=True)
    project.add_argument("--overwrite", action="store_true")
    project.add_argument("--local-ai", metavar="OLLAMA_MODEL",
                         help="opt-in local Ollama at 127.0.0.1:11434 only")
    pack = commands.add_parser("pack-hfs0", help="rebuild an UNSIGNED plain HFS0 table, NOT a playable XCI")
    pack.add_argument("directory", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--hash-prefix", type=int, default=0x200)
    pack.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "project":
            if not (args.xci or args.title_report or args.assets):
                raise ValueError("supply at least --xci, --title-report or --assets")
            report = build_project(args.xci, args.title_report, args.assets)
            # No sensitive data or file bytes ever transmitted by default.
            if args.local_ai:
                report["local_ai_review"] = ask_local_ai(report, args.local_ai)
                report["local_ai_model"] = args.local_ai
            write_report(args.output, report, overwrite=args.overwrite)
            print(args.output.resolve())
        else:
            result = pack_plain_hfs0(
                args.directory, args.output,
                overwrite=args.overwrite, prefix_length=args.hash_prefix
            )
            print(json.dumps(result, indent=2))
    except (ValueError, OSError, json.JSONDecodeError, urllib.error.URLError) as err:
        parser.exit(2, f"XCI project error: {err}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
