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
    if [[ "$pages" =~ ^[0-9]+$ ]] && [ "$pages" -gt 0 ]; then
      printf '%s\n' "$pages"
      return 0
    fi
  fi

  if command -v mdls >/dev/null 2>&1; then
    pages="$(mdls -name kMDItemNumberOfPages -raw "$pdf_file" 2>/dev/null || true)"
    if [[ "$pages" =~ ^[0-9]+$ ]] && [ "$pages" -gt 0 ]; then
      printf '%s\n' "$pages"
      return 0
    fi
  fi

  return 1
}

# Legacy commands accept a single directory component, never a path. Reject
# symlinks on mutable paths, including dangling links, before creating files.
validate_job_workspace() {
  local jobs_dir="$1" slug="$2" path
  if ! [[ "$slug" =~ ^[a-z0-9]+(_[a-z0-9]+)*$ ]]; then
    echo "Invalid company slug: use lowercase letters, numbers and underscores." >&2
    return 1
  fi
  for path in "$jobs_dir" "$jobs_dir/$slug" "$jobs_dir/$slug/pdf" \
    "$jobs_dir/$slug/history" "$jobs_dir/$slug/job_description.txt" \
    "$jobs_dir/$slug/application_questions.txt" \
    "$jobs_dir/$slug/${slug}_resume.md" \
    "$jobs_dir/$slug/${slug}_cover_letter.md" \
    "$jobs_dir/$slug/${slug}_application_answers.md" \
    "$jobs_dir/$slug/pdf/${slug}_resume.pdf" \
    "$jobs_dir/$slug/pdf/${slug}_cover_letter.pdf"; do
    if [ -L "$path" ]; then
      echo "Refusing symlink on mutable workspace path: $path" >&2
      return 1
    fi
  done
  for path in "$jobs_dir/$slug/job_description.txt" \
    "$jobs_dir/$slug/application_questions.txt" \
    "$jobs_dir/$slug/${slug}_resume.md" \
    "$jobs_dir/$slug/${slug}_cover_letter.md" \
    "$jobs_dir/$slug/${slug}_application_answers.md" \
    "$jobs_dir/$slug/pdf/${slug}_resume.pdf" \
    "$jobs_dir/$slug/pdf/${slug}_cover_letter.pdf"; do
    if [ -e "$path" ] && [ ! -f "$path" ]; then
      echo "Expected a regular workspace file: $path" >&2
      return 1
    fi
  done
}
