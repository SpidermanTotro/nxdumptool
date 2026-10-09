# Asset Workbench — accessible game-asset inventory and texture modernization

The asset_workbench.py utility processes **readable local directories** of
assets you created or have permission to work with. It does not decrypt
commercial games, extract NCA or XCI contents, download assets, or create
playable native PC ports.

## Scan: original files unchanged

    python3 tools/asset_workbench.py scan \
      "/path/to/accessible-assets" \
      --report "/path/to/reports/inventory.json"

The JSON report lists filenames, sizes, basic file types, and candidate
character/plant/terrain tags **guessed from filenames only**. It does not
identify a character by viewing its model, nor can it inspect files inside
an encrypted NCA. The optional --hash flag computes SHA-256 hashes.

## Modernize: lossless PNG outputs in a separate directory

Install the Pillow package into a Python virtual environment:

    python3 -m pip install Pillow

Then run:

    python3 tools/asset_workbench.py modernize \
      "/path/to/accessible-assets" \
      "/path/to/separate-outputs" \
      --scale 2 \
      --manifest "/path/to/reports/resizing.json"

PNG/JPEG/WebP/BMP/TIFF/TGA images that Pillow can read are converted into
PNG files, optionally resized 1x–4x with Lanczos interpolation. Originals
remain unchanged. The output folder must not be inside the input folder.
Existing outputs are skipped unless --overwrite is explicitly supplied.
Output filenames include the original extension (e.g. flower.jpg.png) so
different input image formats are not silently merged.

Important: Interpolation does not add true image detail. This tool is not
AI super-resolution; it cannot upgrade encrypted content, reconstruct
character models or make an XCI into a PC executable.

## For a genuine PC port

A native PC port needs assets and game logic that are legally available to
develop against, a rendering and engine runtime, platform-specific work,
licensing, and testing. This utility creates an asset inventory and basic
image conversions only. Future adapters for specific asset formats and
optional locally installed AI upscalers could be added later but are not
part of this commit.

Tests use generated tiny images only:

    python3 -m unittest discover -s tests -p 'test_asset_workbench.py' -v
