#!/usr/bin/env python3
"""Inspect readable assets and batch-upscale ordinary images without touching originals.

Not a decryptor, asset extractor, character-recognition model or native PC port.
Requires Pillow only for image sizing and the 'modernize' subcommand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".tga"}
MODEL_EXT = {".gltf", ".glb", ".obj", ".fbx", ".dae", ".stl", ".blend"}
AUDIO_EXT = {".wav", ".flac", ".ogg", ".mp3", ".opus"}
OPAQUE_EXT = {".nca", ".nsp", ".xci", ".ncz", ".nsz"}
CONTAINER_EXT = {".bfres", ".bntx", ".szs", ".sarc", ".byml", ".astc", ".ktx", ".dds"}
CHARACTER_WORDS = {"character", "actor", "npc", "hero", "enemy", "avatar", "player"}
PLANT_WORDS = {"plant", "tree", "leaf", "leaves", "grass", "flower", "bush", "foliage"}
TERRAIN_WORDS = {"terrain", "landscape", "ground", "rock", "mountain", "water", "river"}
MAX_ENTRIES = 100000

def file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "readable_image"
    if ext in MODEL_EXT:
        return "model_file"
    if ext in AUDIO_EXT:
        return "audio_file"
    if ext in OPAQUE_EXT:
        return "encrypted_or_opaque_container"
    if ext in CONTAINER_EXT:
        return "format_specific_container"
    return "unknown"

def possible_subject(path: Path) -> list[str]:
    tokens = set(re.findall(r"[a-z]+", str(path).lower()))
    tags = []
    if tokens & CHARACTER_WORDS:
        tags.append("possible_character")
    if tokens & PLANT_WORDS:
        tags.append("possible_plant")
    if tokens & TERRAIN_WORDS:
        tags.append("possible_terrain")
    return tags

def valid_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("input must be a real directory, not a symlink")
    return root.resolve(strict=True)

def list_assets(root: Path):
    root = valid_root(root)
    count = 0
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        count += 1
        if count > MAX_ENTRIES:
            raise ValueError("asset count exceeds safety limit")
        relative = candidate.relative_to(root)
        yield relative, candidate

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

def scan(root: Path, include_hashes: bool = False) -> dict:
    source = valid_root(root)
    files = []
    counts: dict[str, int] = {}
    for relative, candidate in list_assets(source):
        kind = file_type(candidate)
        counts[kind] = counts.get(kind, 0) + 1
        item = {
            "path": relative.as_posix(),
            "size_bytes": candidate.stat().st_size,
            "type": kind,
            "candidate_subject_tags": possible_subject(relative),
            "subject_tags_are_filename_guesses": True,
            "content_inspected": False,
        }
        if include_hashes:
            item["sha256"] = sha256(candidate)
        files.append(item)
    return {
        "schema": "nxdt-asset-workbench-v1",
        "source_directory": str(source),
        "mode": "read_only_scan",
        "file_counts": counts,
        "files": files,
        "limitations": [
            "Filename tags are guesses, not recognition of characters or plants.",
            "Encrypted and proprietary containers are inventoried, not decrypted or decoded.",
            "The scan does not demonstrate firmware compatibility or a working PC port.",
        ],
        "pc_port": {
            "status": "planning_only",
            "needed": [
                "Rights-cleared assets and permission or source access",
                "Playable engine and platform-specific rendering/input/audio/runtime",
                "Reimplementation of game logic and save/data compatibility as permitted",
                "Performance, regression and distribution testing",
            ],
        },
    }

def modernize(root: Path, outdir: Path, scale: int, overwrite: bool = False,
              max_pixels: int = 64_000_000) -> dict:
    """Converts recognized ordinary images to lossless PNG, with Lanczos upscaling."""
    source = valid_root(root)
    target = outdir.resolve()
    if target == source or source in target.parents:
        raise ValueError("output directory must not be inside the source directory")
    if scale not in (1, 2, 3, 4):
        raise ValueError("scale must be 1, 2, 3 or 4")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as e:
        raise RuntimeError("Pillow required: python3 -m pip install Pillow") from e

    target.mkdir(parents=True, exist_ok=True)
    converted = []
    skipped = []
    for relative, candidate in list_assets(source):
        if file_type(candidate) != "readable_image":
            skipped.append({"path": relative.as_posix(), "reason": "not_a_supported_image"})
            continue
        dest = target / relative.parent / (relative.name + ".png")
        if dest.exists() and not overwrite:
            skipped.append({"path": relative.as_posix(), "reason": "output_exists"})
            continue
        try:
            with Image.open(candidate) as opened:
                # Refuse decompression bombs or unexpected enormous allocations.
                w, h = opened.size
                if w <= 0 or h <= 0 or w * h * scale * scale > max_pixels:
                    skipped.append({"path": relative.as_posix(), "reason": "pixel_limit"})
                    continue
                image = ImageOps.exif_transpose(opened)
                image.load()
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                if scale > 1:
                    image = image.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Omit embedded source metadata, write atomically via temporary path.
                temporary = dest.with_name(dest.name + ".temporary.png")
                try:
                    image.save(temporary, format="PNG")
                    temporary.replace(dest)
                finally:
                    temporary.unlink(missing_ok=True)
                converted.append({
                    "source": relative.as_posix(),
                    "output": dest.relative_to(target).as_posix(),
                    "original_pixels": [w, h],
                    "output_pixels": [w * scale, h * scale],
                })
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning,
                UnidentifiedImageError, ValueError) as e:
            skipped.append({"path": relative.as_posix(), "reason": "unreadable_image",
                            "detail": type(e).__name__})
    return {
        "schema": "nxdt-asset-workbench-modernization-v1",
        "method": "PNG conversion and Lanczos resampling; does not hallucinate or restore detail",
        "source_directory": str(source),
        "output_directory": str(target),
        "scale": scale,
        "converted": converted,
        "skipped": skipped,
        "source_unchanged": True,
        "pc_port_created": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scanner = commands.add_parser("scan", help="scan a directory of readable assets")
    scanner.add_argument("directory", type=Path)
    scanner.add_argument("--hash", action="store_true", help="hash each file (slower)")
    scanner.add_argument("--report", type=Path, help="write JSON report outside source")
    editor = commands.add_parser("modernize", help="copy/upscale ordinary images to separate directory")
    editor.add_argument("directory", type=Path)
    editor.add_argument("output_directory", type=Path)
    editor.add_argument("--scale", type=int, choices=(1, 2, 3, 4), default=2)
    editor.add_argument("--overwrite", action="store_true")
    editor.add_argument("--manifest", type=Path, help="optional JSON run report")
    args = parser.parse_args()
    try:
        if args.command == "scan":
            result = scan(args.directory, include_hashes=args.hash)
            report = args.report
        else:
            result = modernize(args.directory, args.output_directory,
                               scale=args.scale, overwrite=args.overwrite)
            report = args.manifest
        json_string = json.dumps(result, indent=2) + "\n"
        if report:
            # Only allow report outside original content directory.
            original = valid_root(args.directory)
            location = report.resolve()
            if location == original or original in location.parents:
                raise ValueError("report must be outside the input directory")
            location.parent.mkdir(parents=True, exist_ok=True)
            with location.open("x" if not (args.command == "modernize" and args.overwrite)
                               else "w", encoding="utf-8") as f:
                f.write(json_string)
            print(location)
        else:
            print(json_string, end="")
    except (ValueError, OSError, RuntimeError) as e:
        parser.exit(2, f"Asset workbench failed: {e}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
