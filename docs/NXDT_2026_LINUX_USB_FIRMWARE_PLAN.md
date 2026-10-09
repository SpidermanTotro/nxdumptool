# nxdumptool Linux host and 2026 firmware-verification plan

Status: working planning notes on the isolated candidate branch. **Not a published release.**

## Existing features already implemented
- Switch USB ABI 1.4 via device 057e:3000; Python host uses libusb/PyUSB.
- Fedora/Linux udev manual permissions documented in host/README.md.
- Background gamecard insertion/ejection status notifications already implemented.
- System Update CNMT signature checks, matching of update content versions, NCA SHA-256 dump verification, and SystemVersion file reading.
- Codespace transcript reports added title metadata tabs and SystemVersion read-only comparison. These changes are not yet on this remote branch.

## Linux USB: read-only diagnostics and optional rule installation
Run from the repository root:

    bash host/linux_usb_setup.sh

The script checks USB visibility and PyUSB/libusb dependencies without changing anything.
Only if permissions fail, explicitly install the rule:

    bash host/linux_usb_setup.sh --install-rule

The rule restricts access to nxdumptool 057e:3000. **RCM/APX is 0955:7321 and requires different handling**.
For Fedora:

    sudo dnf install python3 libusb1 usbutils
    python3 -m venv .venv
    source .venv/bin/activate
    python3 -m pip install -r host/requirements.txt
    python3 host/nxdt_host.py

## Requested 2026 enhancements — distinct from already-working features
1. **SystemVersion verifier UI:** show explicit Verified / Mismatch / Unknown based on signed data, numeric version, display string, runtime HOS; candidate local Codespace source needs CI and on-device testing.
2. **Better dumping text:** title, gamecard or installed content source, base/update/DLC type, version, elapsed time, transferred bytes, hash-verification status, and actionable errors. NOT YET IMPLEMENTED.
3. **Linux USB improvements:** retry safe failure cases, cancellation and explicit resume verification; preflight script added, data-transfer rewrite NOT YET IMPLEMENTED.
4. **Game auto-detection:** already present for inserted/ejected cards; proposed richer title refresh and version labels, not a duplicated detector.
5. **Game update version checks:** report installed version and version information available from lawful gamecard metadata; distinguish *installed*, *bundled* and *latest known* and do not guess update availability.
6. **Download updates:** the repository has no official Nintendo update-download interface. Do not ship proprietary firmware/content, keys or unofficial CDN bypass. Use official updating and local read-only metadata reports.
7. **Local verification manifest:** optional JSON file with title IDs, versions, content sizes, SHA-256, and result states; exclude secrets.
8. **Title search/filter and queued exports:** stage after validating the already-edited title-details popup.

## Candidate release gates
- Push current local Codespace source edits to release/23.0.1-validation-20261009.
- Run candidate workflow for both PoC and UI; verify ELF/NRO files and SHA-256.
- Verify real Switch firmware 23.0.1 on hardware, including error and permission handling.
- Fix or characterize the exception stack linker warning.
- Do not confuse application version 23.0.1 with confirmed runtime compatibility.
- Publish no release until the candidate is reviewed and manually approved.
