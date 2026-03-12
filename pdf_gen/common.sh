#!/usr/bin/env bash

PDF_ENGINE_PRIORITY=("wkhtmltopdf" "weasyprint" "tectonic")
PDF_ENGINE_INSTALL_ORDER_BREW=("weasyprint" "tectonic")
PDF_ENGINE_INSTALL_ORDER_APT=("wkhtmltopdf" "weasyprint" "tectonic")

detect_pdf_engine() {
  local engine

  for engine in "${PDF_ENGINE_PRIORITY[@]}"; do
    if command -v "$engine" >/dev/null 2>&1; then
      printf '%s\n' "$engine"
      return 0
    fi
  done

  return 1
}

get_pdf_page_count() {
  local pdf_file="$1"
  local pages=""

  if command -v pdfinfo >/dev/null 2>&1; then
    pages="$(pdfinfo "$pdf_file" 2>/dev/null | awk '/^Pages:/ {print $2; exit}')"
    if [[ "$pages" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "$pages"
      return 0
    fi
  fi

  if command -v mdls >/dev/null 2>&1; then
    pages="$(mdls -name kMDItemNumberOfPages -raw "$pdf_file" 2>/dev/null || true)"
    if [[ "$pages" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "$pages"
      return 0
    fi
  fi

  return 1
}
