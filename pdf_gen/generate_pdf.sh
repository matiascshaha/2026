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

mkdir -p "$PDF_DIR"

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc is not installed. Run ./setup.sh first."
  exit 1
fi

if ! pdf_engine="$(detect_pdf_engine)"; then
  echo "No supported PDF engine found. Run ./setup.sh first."
  echo "Supported engines: ${PDF_ENGINE_PRIORITY[*]}"
  exit 1
fi

shopt -s nullglob
md_files=("$ROOT_DIR"/*.md)

if [ ${#md_files[@]} -eq 0 ]; then
  echo "No .md files found in $ROOT_DIR"
  exit 1
fi

for md_file in "${md_files[@]}"; do
  base_name="$(basename "$md_file" .md)"
  pdf_file="$PDF_DIR/${base_name}.pdf"

  echo "Converting $(basename "$md_file") -> pdf/${base_name}.pdf"

  pandoc \
    "$md_file" \
    -o "$pdf_file" \
    --from=gfm \
    --pdf-engine="$pdf_engine" \
    --metadata title="$base_name"
done

echo "Done. PDFs created in $PDF_DIR using $pdf_engine"
