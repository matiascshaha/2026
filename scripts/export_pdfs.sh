#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_SH="$PROJECT_ROOT/pdf_gen/common.sh"
JOBS_DIR="$PROJECT_ROOT/jobs"
PDF_CSS="$PROJECT_ROOT/templates/pdf_compact.css"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/export_pdfs.sh --company <company_slug> [--max-resume-pages N] [--max-cover-letter-pages N] [--no-page-check]
EOF
}

derive_doc_title() {
  local md_file="$1"
  local base_name
  local first_line

  base_name="$(basename "$md_file" .md)"
  first_line="$(awk 'NF {print; exit}' "$md_file" | sed -E 's/^# +//; s/[[:space:]]+$//')"

  if [[ "$base_name" == *_resume ]]; then
    if [ -n "$first_line" ]; then
      printf '%s Resume\n' "$first_line"
      return
    fi
    printf 'Resume\n'
    return
  fi

  if [[ "$base_name" == *_cover_letter ]]; then
    if [ -n "$first_line" ]; then
      printf '%s Cover Letter\n' "$first_line"
      return
    fi
    printf 'Cover Letter\n'
    return
  fi

  if [ -n "$first_line" ]; then
    printf '%s\n' "$first_line"
    return
  fi

  printf '%s\n' "$base_name"
}

if [ ! -f "$COMMON_SH" ]; then
  echo "Missing helper file: $COMMON_SH"
  exit 1
fi

if [ ! -f "$PDF_CSS" ]; then
  echo "Missing PDF stylesheet: $PDF_CSS"
  exit 1
fi

# shellcheck source=../pdf_gen/common.sh
source "$COMMON_SH"

company_slug=""
max_resume_pages=1
max_cover_letter_pages=1
enforce_page_check=1

while [ $# -gt 0 ]; do
  case "$1" in
    --company)
      company_slug="${2:-}"
      shift 2
      ;;
    --max-resume-pages)
      max_resume_pages="${2:-}"
      shift 2
      ;;
    --max-cover-letter-pages)
      max_cover_letter_pages="${2:-}"
      shift 2
      ;;
    --no-page-check)
      enforce_page_check=0
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [ -z "$company_slug" ]; then
  echo "--company is required."
  usage
  exit 1
fi

if ! [[ "$max_resume_pages" =~ ^[0-9]+$ ]] || [ "$max_resume_pages" -lt 1 ]; then
  echo "--max-resume-pages must be a positive integer."
  exit 1
fi

if ! [[ "$max_cover_letter_pages" =~ ^[0-9]+$ ]] || [ "$max_cover_letter_pages" -lt 1 ]; then
  echo "--max-cover-letter-pages must be a positive integer."
  exit 1
fi

if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc is not installed. Run ./scripts/setup_pdf_tools.sh first."
  exit 1
fi

if ! pdf_engine="$(detect_pdf_engine)"; then
  echo "No supported PDF engine found. Run ./scripts/setup_pdf_tools.sh first."
  echo "Supported engines: ${PDF_ENGINE_PRIORITY[*]}"
  exit 1
fi

job_dir="$JOBS_DIR/$company_slug"
pdf_dir="$job_dir/pdf"

if [ ! -d "$job_dir" ]; then
  echo "Company job directory not found: $job_dir"
  exit 1
fi

mkdir -p "$pdf_dir"

files=(
  "$job_dir/${company_slug}_resume.md"
  "$job_dir/${company_slug}_cover_letter.md"
)

converted_count=0
page_violations=0
page_check_failed=0
for md_file in "${files[@]}"; do
  if [ ! -f "$md_file" ]; then
    continue
  fi

  base_name="$(basename "$md_file" .md)"
  pdf_file="$pdf_dir/${base_name}.pdf"
  doc_title="$(derive_doc_title "$md_file")"

  echo "Converting $(basename "$md_file") -> $(basename "$pdf_file")"
  pandoc_args=(
    "$md_file"
    -o "$pdf_file"
    --from=gfm
    --pdf-engine="$pdf_engine"
    --metadata "title=$doc_title"
  )

  if [ "$pdf_engine" != "tectonic" ]; then
    pandoc_args+=(--css "$PDF_CSS")
  fi

  pandoc \
    "${pandoc_args[@]}"

  if [ "$enforce_page_check" -eq 1 ]; then
    max_pages="$max_cover_letter_pages"
    if [[ "$base_name" == *_resume ]]; then
      max_pages="$max_resume_pages"
    fi

    if pages="$(get_pdf_page_count "$pdf_file")"; then
      echo "  pages: $pages (limit: $max_pages)"
      if [ "$pages" -gt "$max_pages" ]; then
        echo "  ERROR: $(basename "$pdf_file") exceeds page limit ($pages > $max_pages)"
        page_violations=$((page_violations + 1))
      fi
    else
      echo "  ERROR: could not determine page count for $(basename "$pdf_file")"
      page_check_failed=1
    fi
  fi

  converted_count=$((converted_count + 1))
done

if [ "$converted_count" -eq 0 ]; then
  echo "No output markdown files found in $job_dir"
  echo "Expected:"
  echo "  - $job_dir/${company_slug}_resume.md"
  echo "  - $job_dir/${company_slug}_cover_letter.md"
  exit 1
fi

if [ "$enforce_page_check" -eq 1 ] && [ "$page_violations" -gt 0 ]; then
  echo "Export completed, but $page_violations file(s) exceeded page limits."
  echo "Either tighten the markdown content or run with larger limits."
  exit 2
fi

if [ "$enforce_page_check" -eq 1 ] && [ "$page_check_failed" -eq 1 ]; then
  echo "Export completed, but page checking failed."
  echo "Run ./scripts/setup_pdf_tools.sh to install page-check dependencies, or rerun with --no-page-check."
  exit 3
fi

echo "Done. PDFs created in $pdf_dir using $pdf_engine"
