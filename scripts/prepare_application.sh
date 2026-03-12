#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_DIR="$PROJECT_ROOT/context"
INTAKE_DIR="$PROJECT_ROOT/intake"
JOBS_DIR="$PROJECT_ROOT/jobs"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/prepare_application.sh --company <company_name_or_slug> [--job-description <path>] [--snapshot]

Examples:
  ./scripts/prepare_application.sh --company Apple --job-description ./intake/job_description.txt
  ./scripts/prepare_application.sh --company Apple --snapshot
  ./scripts/prepare_application.sh --company robinhood
EOF
}

slugify() {
  local raw="$1"
  printf '%s' "$raw" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//'
}

sanitize_job_description() {
  local src="$1"
  local dst="$2"

  awk '
    BEGIN { skip = 0 }
    {
      line = tolower($0)
      if (line ~ /^[[:space:]]*#*[[:space:]]*compressed summary[[:space:]]*$/) {
        skip = 1
      }
      if (skip == 0) {
        print
      }
    }
  ' "$src" > "$dst"

  # Trim trailing empty lines.
  sed -i '' -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$dst"
}

snapshot_existing_outputs_if_needed() {
  local job_dir="$1"
  local company_slug="$2"
  local job_description_changed="$3"

  local resume_file="$job_dir/${company_slug}_resume.md"
  local cover_letter_file="$job_dir/${company_slug}_cover_letter.md"
  local answers_file="$job_dir/${company_slug}_application_answers.md"
  local job_description_file="$job_dir/job_description.txt"
  local questions_file="$job_dir/application_questions.txt"
  local pdf_resume="$job_dir/pdf/${company_slug}_resume.pdf"
  local pdf_cover="$job_dir/pdf/${company_slug}_cover_letter.pdf"

  if [ "$job_description_changed" -eq 0 ] && [ "$force_snapshot" -eq 0 ]; then
    return
  fi

  if [ ! -f "$resume_file" ] && [ ! -f "$cover_letter_file" ] && [ ! -f "$answers_file" ]; then
    return
  fi

  local timestamp
  local snapshot_dir
  timestamp="$(date +%Y%m%d_%H%M%S)"
  snapshot_dir="$job_dir/history/$timestamp"

  mkdir -p "$snapshot_dir/pdf"

  for file in "$job_description_file" "$questions_file" "$resume_file" "$cover_letter_file" "$answers_file"; do
    if [ -f "$file" ]; then
      cp "$file" "$snapshot_dir/"
    fi
  done

  for file in "$pdf_resume" "$pdf_cover"; do
    if [ -f "$file" ]; then
      cp "$file" "$snapshot_dir/pdf/"
    fi
  done

  snapshot_reason="job_description_changed"
  if [ "$job_description_changed" -eq 0 ]; then
    snapshot_reason="forced_snapshot"
  fi

  cat > "$snapshot_dir/snapshot_note.txt" <<EOF
Snapshot created automatically before regeneration.
Timestamp: $timestamp
Company slug: $company_slug
Reason: $snapshot_reason
EOF

  echo "Snapshot created: $snapshot_dir"
}

ensure_canonical_inputs() {
  mkdir -p "$CONTEXT_DIR" "$INTAKE_DIR"

  if [ ! -f "$CONTEXT_DIR/master_brag_sheet.md" ]; then
    if [ -f "$PROJECT_ROOT/master_brag_sheet.md" ]; then
      cp "$PROJECT_ROOT/master_brag_sheet.md" "$CONTEXT_DIR/master_brag_sheet.md"
    elif [ -f "$PROJECT_ROOT/brag_sheet.md" ]; then
      cp "$PROJECT_ROOT/brag_sheet.md" "$CONTEXT_DIR/master_brag_sheet.md"
    fi
  fi

  if [ ! -f "$CONTEXT_DIR/resume_base.md" ] && [ -f "$PROJECT_ROOT/resume_base.md" ]; then
    cp "$PROJECT_ROOT/resume_base.md" "$CONTEXT_DIR/resume_base.md"
  fi

  if [ ! -f "$CONTEXT_DIR/preferences.md" ] && [ -f "$PROJECT_ROOT/preferences.md" ]; then
    cp "$PROJECT_ROOT/preferences.md" "$CONTEXT_DIR/preferences.md"
  fi

  if [ ! -f "$INTAKE_DIR/job_description.txt" ]; then
    if [ -f "$PROJECT_ROOT/job_description.txt" ]; then
      cp "$PROJECT_ROOT/job_description.txt" "$INTAKE_DIR/job_description.txt"
    fi
  fi
}

company_input=""
job_description_path=""
force_snapshot=0

while [ $# -gt 0 ]; do
  case "$1" in
    --company)
      company_input="${2:-}"
      shift 2
      ;;
    --job-description)
      job_description_path="${2:-}"
      shift 2
      ;;
    --snapshot)
      force_snapshot=1
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

if [ -z "$company_input" ]; then
  echo "--company is required."
  usage
  exit 1
fi

ensure_canonical_inputs

if [ ! -f "$CONTEXT_DIR/master_brag_sheet.md" ]; then
  echo "Missing master brag sheet: $CONTEXT_DIR/master_brag_sheet.md"
  exit 1
fi

if [ ! -f "$CONTEXT_DIR/resume_base.md" ]; then
  echo "Missing resume base: $CONTEXT_DIR/resume_base.md"
  exit 1
fi

if [ ! -f "$CONTEXT_DIR/preferences.md" ]; then
  echo "Missing preferences: $CONTEXT_DIR/preferences.md"
  exit 1
fi

if [ ! -f "$CONTEXT_DIR/resume_quality_guide.md" ]; then
  echo "Missing resume quality guide: $CONTEXT_DIR/resume_quality_guide.md"
  exit 1
fi

if [ ! -f "$CONTEXT_DIR/profile_links.md" ]; then
  echo "Missing profile links file: $CONTEXT_DIR/profile_links.md"
  exit 1
fi

if [ -z "$job_description_path" ]; then
  job_description_path="$INTAKE_DIR/job_description.txt"
fi

if [ ! -f "$job_description_path" ]; then
  echo "Missing job description file: $job_description_path"
  exit 1
fi

company_slug="$(slugify "$company_input")"
job_dir="$JOBS_DIR/$company_slug"
resume_file="$job_dir/${company_slug}_resume.md"
cover_letter_file="$job_dir/${company_slug}_cover_letter.md"
current_job_description="$job_dir/job_description.txt"
sanitized_job_description="$(mktemp)"

mkdir -p "$job_dir/pdf"

sanitize_job_description "$job_description_path" "$sanitized_job_description"
job_description_changed=1
if [ -f "$current_job_description" ] && cmp -s "$current_job_description" "$sanitized_job_description"; then
  job_description_changed=0
fi

snapshot_existing_outputs_if_needed "$job_dir" "$company_slug" "$job_description_changed"

ln -sfn "$PROJECT_ROOT/AGENTS.md" "$job_dir/AGENTS.md"
ln -sfn "$CONTEXT_DIR/master_brag_sheet.md" "$job_dir/master_brag_sheet.md"
ln -sfn "$CONTEXT_DIR/resume_base.md" "$job_dir/resume_base.md"
ln -sfn "$CONTEXT_DIR/preferences.md" "$job_dir/preferences.md"
ln -sfn "$CONTEXT_DIR/resume_quality_guide.md" "$job_dir/resume_quality_guide.md"
ln -sfn "$CONTEXT_DIR/profile_links.md" "$job_dir/profile_links.md"
mv "$sanitized_job_description" "$job_dir/job_description.txt"
chmod 644 "$job_dir/job_description.txt"

questions_file="$job_dir/application_questions.txt"
if [ -f "$INTAKE_DIR/application_questions.txt" ]; then
  cp "$INTAKE_DIR/application_questions.txt" "$questions_file"
fi

if [ ! -f "$resume_file" ]; then
  cat > "$resume_file" <<EOF
# ${company_slug}_resume
EOF
fi

if [ ! -f "$cover_letter_file" ]; then
  cat > "$cover_letter_file" <<EOF
# ${company_slug}_cover_letter
EOF
fi

if [ -f "$questions_file" ]; then
  "$PROJECT_ROOT/scripts/generate_application_answers.sh" \
    --company "$company_slug" \
    --questions "$questions_file"
fi

echo "Application workspace ready: $job_dir"
echo "Expected outputs:"
echo "  - $resume_file"
echo "  - $cover_letter_file"
echo "  - $job_dir/${company_slug}_application_answers.md"
echo
echo "Next:"
echo "  1) Ask Codex: generate $company_slug resume + cover letter from AGENTS.md"
echo "  2) Run: \"$PROJECT_ROOT/scripts/export_pdfs.sh\" --company \"$company_slug\""
