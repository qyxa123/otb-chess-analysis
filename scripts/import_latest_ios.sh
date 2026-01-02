#!/bin/bash
# Pull the newest video from iPhone DCIM using libimobiledevice/ifuse.
set -euo pipefail

INBOX_DIR="${INBOX_DIR:-$HOME/OTBReview/inbox}"
MOUNT_POINT="${MOUNT_POINT:-/tmp/iphone_dcim}"

command -v idevicepair >/dev/null || { echo "idevicepair not found (brew install libimobiledevice)."; exit 1; }
command -v ifuse >/dev/null || { echo "ifuse not found (brew install ifuse)."; exit 1; }

mkdir -p "$INBOX_DIR" "$MOUNT_POINT"

# Pair/trust the device if needed.
if ! idevicepair validate >/dev/null 2>&1; then
  echo "Pairing with device; confirm trust on iPhone..."
  idevicepair pair
fi

# Mount DCIM.
if ! mount | grep -q "$MOUNT_POINT"; then
  ifuse "$MOUNT_POINT"
fi

# Grab the newest MOV/MP4 from DCIM.
LATEST=$(find "$MOUNT_POINT" -maxdepth 3 -type f \( -iname "*.mov" -o -iname "*.mp4" -o -iname "*.m4v" \) -print0 |
  xargs -0 ls -t | head -n 1)

if [ -z "$LATEST" ]; then
  echo "No video found in DCIM. Record once, then rerun."
  exit 1
fi

DEST="$INBOX_DIR/$(basename "$LATEST")"
cp "$LATEST" "$DEST"
echo "Copied $(basename "$LATEST") to $DEST"

# Optional: unmount when done
if mount | grep -q "$MOUNT_POINT"; then
  if command -v fusermount >/dev/null 2>&1; then
    fusermount -u "$MOUNT_POINT" || true
  else
    umount "$MOUNT_POINT" || true
  fi
fi
