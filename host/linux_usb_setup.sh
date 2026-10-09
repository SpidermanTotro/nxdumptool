#!/usr/bin/env bash
# Linux helper for nxdumptool USB (057e:3000). --check is read-only.
set -euo pipefail
RULE_PATH="/etc/udev/rules.d/70-nxdumptool.rules"
RULE='SUBSYSTEM=="usb", ATTRS{idVendor}=="057e", ATTRS{idProduct}=="3000", MODE="0660", TAG+="uaccess"'
usage() {
  printf '%s\n' \
    'Usage: bash host/linux_usb_setup.sh [--check | --install-rule]' \
    ' --check: read-only USB/libusb prerequisite check (default)' \
    ' --install-rule: explicitly install the nxdumptool-only udev rule' \
    ' This is not the RCM device (0955:7321).'
}
if [[ "$(uname -s)" != "Linux" ]]; then echo "Linux only" >&2; exit 1; fi
action="--check"
if (( $# > 0 )); then action="$1"; fi
case "$action" in
  --check) ;;
  --install-rule)
    if [[ -f "$RULE_PATH" ]]; then
      existing="$(tr -d '\r' < "$RULE_PATH")"
      if [[ "$existing" == "$RULE" ]]; then
        echo "Matching udev rule already present."
      else
        echo "Conflicting rule found; refusing to overwrite $RULE_PATH" >&2
        exit 1
      fi
    else
      tmp="$(mktemp)"
      trap 'rm -f "$tmp"' EXIT
      printf '%s\n' "$RULE" > "$tmp"
      if (( EUID == 0 )); then
        install -m 0644 "$tmp" "$RULE_PATH"
      else
        command -v sudo >/dev/null || { echo "sudo required" >&2; exit 1; }
        sudo install -m 0644 "$tmp" "$RULE_PATH"
      fi
      echo "Installed udev rule: $RULE_PATH"
    fi
    if command -v udevadm >/dev/null; then
      if (( EUID == 0 )); then
        udevadm control --reload-rules
        udevadm trigger --subsystem-match=usb
      else
        sudo udevadm control --reload-rules
        sudo udevadm trigger --subsystem-match=usb
      fi
      echo "Rule reloaded. Reconnect USB cable if necessary."
    else
      echo "udevadm is unavailable; reconnect/reboot when convenient."
    fi
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
echo "nxdumptool Linux USB preflight: expected device 057e:3000"
if command -v lsusb >/dev/null; then
  if lsusb -d 057e:3000; then
    echo "Device visible; now verify host program access."
  else
    echo "Not detected. Launch nxdumptool on Switch, then reconnect USB."
  fi
else
  echo "lsusb missing: Fedora sudo dnf install usbutils"
fi
if command -v python3 >/dev/null; then
  python3 - <<'PY'
import ctypes.util
import importlib.util
print("PyUSB:", "installed" if importlib.util.find_spec("usb") else "MISSING: install host/requirements.txt in a venv")
print("libusb 1.0:", "available" if ctypes.util.find_library("usb-1.0") else "MISSING: Fedora sudo dnf install libusb1")
PY
else
  echo "Python 3 missing."
fi
if [[ -f "$RULE_PATH" ]]; then
  echo "udev rule exists: $RULE_PATH"
else
  echo "udev rule absent. Only if permissions fail, use --install-rule."
fi
echo "Launch the existing host: python3 host/nxdt_host.py"
