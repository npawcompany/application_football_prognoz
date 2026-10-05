#!/usr/bin/env bash
# Export docs/vkr/manuscript/figures/drawio/*.drawio to PNG
# with the official diagrams.net desktop CLI (not the PIL fallback).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="31.7.0"
DEB_NAME="drawio-amd64-${VERSION}.deb"
DEB_URL="https://github.com/jgraph/drawio-desktop/releases/download/v${VERSION}/${DEB_NAME}"
CACHE_DIR="${DRAWIO_CACHE_DIR:-$ROOT/.cache}"
CACHE_DEB="$CACHE_DIR/$DEB_NAME"
SRC_DIR="$ROOT/docs/vkr/manuscript/figures/drawio"

if ! command -v drawio >/dev/null 2>&1; then
  mkdir -p "$CACHE_DIR"
  if [[ ! -f "$CACHE_DEB" ]]; then
    echo "Downloading ${DEB_URL}"
    curl -fL --retry 3 -o "$CACHE_DEB.partial" "$DEB_URL"
    mv "$CACHE_DEB.partial" "$CACHE_DEB"
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y "$CACHE_DEB" || {
      sudo dpkg -i "$CACHE_DEB" || true
      sudo apt-get install -f -y
    }
  else
    apt-get update
    apt-get install -y "$CACHE_DEB" || {
      dpkg -i "$CACHE_DEB" || true
      apt-get install -f -y
    }
  fi
fi

if ! command -v xvfb-run >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get install -y xvfb
  else
    apt-get install -y xvfb
  fi
fi

shopt -s nullglob
files=("$SRC_DIR"/*.drawio)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "No .drawio files in $SRC_DIR" >&2
  exit 1
fi

for src in "${files[@]}"; do
  base="$(basename "$src" .drawio)"
  out="$SRC_DIR/${base}.png"
  echo "Export $src -> $out"
  xvfb-run -a drawio --no-sandbox -x -f png -s 2 -b 12 -o "$out" "$src"
done

echo "Exported ${#files[@]} diagram(s) into $SRC_DIR"
