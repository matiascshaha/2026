#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF_DIR="$ROOT_DIR/pdf"
COMMON_SH="$ROOT_DIR/common.sh"

if [ ! -f "$COMMON_SH" ]; then
  echo "Missing helper file: $COMMON_SH"
  exit 1
fi

# shellcheck source=./common.sh
source "$COMMON_SH"

install_with_brew() {
  if ! command -v pandoc >/dev/null 2>&1; then
    brew install pandoc
  fi

  if ! command -v pdfinfo >/dev/null 2>&1; then
    brew install poppler
  fi

  if detect_pdf_engine >/dev/null 2>&1; then
    return
  fi

  local candidate
  for candidate in "${PDF_ENGINE_INSTALL_ORDER_BREW[@]}"; do
    if brew install "$candidate"; then
      return
    fi
  done
}

install_with_apt() {
  sudo apt-get update

  if ! command -v pandoc >/dev/null 2>&1; then
    sudo apt-get install -y pandoc
  fi

  if ! command -v pdfinfo >/dev/null 2>&1; then
    sudo apt-get install -y poppler-utils
  fi

  if detect_pdf_engine >/dev/null 2>&1; then
    return
  fi

  local candidate
  for candidate in "${PDF_ENGINE_INSTALL_ORDER_APT[@]}"; do
    if sudo apt-get install -y "$candidate"; then
      return
    fi
  done
}

mkdir -p "$PDF_DIR"

if command -v brew >/dev/null 2>&1; then
  install_with_brew
elif command -v apt-get >/dev/null 2>&1; then
  install_with_apt
else
  echo "Unsupported package manager. Install pandoc and one of: ${PDF_ENGINE_PRIORITY[*]}."
  exit 1
fi

if ! pdf_engine="$(detect_pdf_engine)"; then
  echo "No supported PDF engine found. Install one of: ${PDF_ENGINE_PRIORITY[*]}."
  exit 1
fi

if ! command -v pdfinfo >/dev/null 2>&1; then
  echo "Warning: pdfinfo not found. Page-limit checks may be unavailable."
fi

echo "Setup complete."
echo "PDF engine: $pdf_engine"
echo "Put your .md files directly in: $ROOT_DIR"
echo "Generated PDFs will go in: $PDF_DIR"
