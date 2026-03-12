#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_DIR="$PROJECT_ROOT/context"
INTAKE_DIR="$PROJECT_ROOT/intake"
JOBS_DIR="$PROJECT_ROOT/jobs"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/generate_application_answers.sh --company <company_slug> [--questions <path>] [--overwrite]
EOF
}

company_slug=""
questions_path="$INTAKE_DIR/application_questions.txt"
overwrite=0

while [ $# -gt 0 ]; do
  case "$1" in
    --company)
      company_slug="${2:-}"
      shift 2
      ;;
    --questions)
      questions_path="${2:-}"
      shift 2
      ;;
    --overwrite)
      overwrite=1
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

job_dir="$JOBS_DIR/$company_slug"
out_file="$job_dir/${company_slug}_application_answers.md"
links_file="$CONTEXT_DIR/profile_links.md"

if [ ! -d "$job_dir" ]; then
  echo "Company job directory not found: $job_dir"
  exit 1
fi

if [ ! -f "$links_file" ]; then
  echo "Missing profile links file: $links_file"
  exit 1
fi

if [ ! -f "$questions_path" ]; then
  echo "Questions file not found: $questions_path"
  exit 1
fi

if [ -f "$out_file" ] && [ "$overwrite" -ne 1 ]; then
  echo "Answers file already exists: $out_file"
  echo "Use --overwrite to regenerate."
  exit 0
fi

linkedin_url="$(sed -n 's/^LinkedIn:[[:space:]]*//p' "$links_file" | head -n 1)"
github_url="$(sed -n 's/^GitHub:[[:space:]]*//p' "$links_file" | head -n 1)"
website_url="$(sed -n 's/^Website:[[:space:]]*//p' "$links_file" | head -n 1)"

{
  echo "# ${company_slug} Application Answers"
  echo
  echo "## Links"
  echo "LinkedIn: ${linkedin_url}"
  echo "GitHub: ${github_url}"
  echo "Website: ${website_url}"
  echo
  echo "## Questions And Answers"
  echo
} > "$out_file"

question_count=0
while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line="$(printf '%s' "$raw_line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  line="${line#- }"
  line="$(printf '%s' "$line" | sed -E 's/^[0-9]+\.[[:space:]]+//')"

  if [ -z "$line" ]; then
    continue
  fi

  if [[ "$line" == \#* ]]; then
    continue
  fi

  question_count=$((question_count + 1))
  {
    echo "### Q${question_count}. ${line}"
    echo "A:"
    echo
  } >> "$out_file"
done < "$questions_path"

if [ "$question_count" -eq 0 ]; then
  cat >> "$out_file" <<'EOF'
### Q1. Why do you want to work here?
A:

EOF
fi

echo "Generated: $out_file"
