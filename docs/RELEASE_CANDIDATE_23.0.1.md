# nxdumptool 23.0.1 release-candidate checklist
Date: 2026-10-09
Status: Candidate; **not a published release and not yet hardware-certified**.

## What was actually seen
- A Codespace log showed successful local builds of the PoC and UI, with both NROs and ELFs.
- The local Makefile identified the build as 23.0.1.
- Four tracked files remained changed locally: Makefile, source/core/keys.c, source/views/titles_tab.cpp, romfs/i18n/en-US/titles_tab.json.
- As of this checklist, remote branch rewrite still had version 2.0.0 and the placeholder Red/Green/Blue title tabs.
- Official Nintendo system version 23.0.1 exists. Compiling an app tagged 23.0.1 does not prove its runtime compatibility with system firmware 23.0.1.

## Why validation is on a separate branch
The existing .github/workflows/rewrite.yml has a release-action step that may update the rewrite-prerelease tag on pushes to rewrite. Do not push unchecked changes straight to rewrite. This new workflow deliberately uploads CI artifacts only and does **not** publish a GitHub release.

## Carry the four local edits from Codespace
Run in your Codespace, after checking the current directory is the modified nxdumptool checkout:

    git remote -v
    git status --short
    git diff --binary > /tmp/nxdumptool-23.0.1-local-backup.patch
    git fetch origin
    git switch -c release/23.0.1-validation-20261009 --track origin/release/23.0.1-validation-20261009
    git add Makefile source/core/keys.c source/views/titles_tab.cpp romfs/i18n/en-US/titles_tab.json
    git -c core.whitespace=cr-at-eol diff --cached --check
    git commit -m "Prepare nxdumptool 23.0.1 candidate metadata and title views"
    git push -u origin release/23.0.1-validation-20261009

IMPORTANT: Before pushing, verify that git remote -v points to SpidermanTotro/nxdumptool. If the switch fails because of local changes, stop and inspect; do not reset, clean, or discard work.

Then open a pull request into rewrite to run the candidate verification workflow. Inspect CI artifacts and on-device tests before merging or publishing.

## 2026 feature comparison
- Current source: signed System Update Meta NCA verification; version equality of each title vs system-update content metadata; streaming SHA-256 verification of NCA content; parsing of SystemVersion file.
- Codespace candidate change: real per-title metadata tabs replace red/green/blue placeholders.
- Still recommended: read-only SystemVersion-vs-HOS version report; per-component update version validation report; explicit warnings about missing update and DLC records; searchable sortable title lists; verification export JSON with hashes and firmware labels; regression tests across 22.x, 23.0.0, 23.0.1.
- Never assume 23.0.1 introduces a new master-key generation without evidence. No firmware keys or encrypted game content should be put in CI artifacts.

## Release gates
1. Confirm four source edits pushed to candidate branch.
2. Candidate workflow passes all checks for both NRO and ELF.
3. Test homebrew launches on target Switch firmware with an unmodified setup.
4. Verify SystemVersion/CNMT values from lawful test sources, failure paths, and hash handling.
5. Resolve or document __nx_exception_stack linker warning.
6. Publish **only after** explicit review of candidate binaries, checksums, and release notes.
