#!/usr/bin/env python3
"""Read-only local context retrieval for agents. No network calls or application submission."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
CONTEXT_FILES = (
    "master_brag_sheet.md", "resume_base.md", "preferences.md",
    "resume_quality_guide.md", "profile_links.md",
)


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def metadata(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "content"}


def field(content: str, label: str) -> str | None:
    match = re.search(rf"^{re.escape(label)}:[ \t]*(.*)$", content, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    if value:
        return value
    # Some existing fields put their value on the next nonempty line.
    for line in content[match.end():].splitlines():
        if line.strip():
            if re.match(r"^(?:#{1,6}\s|[A-Za-z][A-Za-z /-]*:)", line.strip()):
                return None
            return line.strip()
    return None


def load_context(root: Path) -> dict:
    documents, achievements, sections = [], [], []
    seen_ids = set()
    for name in CONTEXT_FILES:
        path = root / "context" / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Context source escapes repository: context/{name}")
        # Decode raw bytes to preserve line endings and hash the actual UTF-8 source.
        content = path.read_bytes().decode("utf-8")
        if not content.strip():
            raise ValueError(f"Empty context source: context/{name}")
        lines = content.splitlines()
        document = {"id": "document_" + Path(name).stem, "path": f"context/{name}",
                    "sha256": digest(content), "line_count": len(lines), "content": content}
        documents.append(document)
        if name == "master_brag_sheet.md":
            starts = [i for i, line in enumerate(lines) if line.strip() == "## Achievement"]
            if not starts:
                raise ValueError("Brag sheet has no '## Achievement' sections")
            for start, end in zip(starts, starts[1:] + [len(lines)]):
                entry = "\n".join(lines[start:end]).strip()
                title = field(entry, "Title")
                if not title:
                    raise ValueError(f"Achievement at line {start + 1} is missing Title")
                evidence_id = "achievement_" + digest(title.casefold())[:16]
                if evidence_id in seen_ids:
                    raise ValueError(f"Duplicate achievement title: {title}")
                seen_ids.add(evidence_id)
                tags = field(entry, "Tags")
                achievements.append({"id": evidence_id, "title": title,
                                     "source": f"context/{name}", "source_sha256": document["sha256"],
                                     "line_start": start + 1, "line_end": end,
                                     "context": field(entry, "Context"),
                                     "organization": field(entry, "Organization"),
                                     "tags": [tag.strip() for tag in tags.split(",")] if tags else [],
                                     "content": entry})
        else:
            starts = [i for i, line in enumerate(lines) if re.match(r"^#{1,6}\s+", line)]
            if not starts or starts[0] != 0:
                starts.insert(0, 0)
            occurrences = {}
            for start, end in zip(starts, starts[1:] + [len(lines)]):
                entry = "\n".join(lines[start:end]).strip()
                if not entry:
                    continue
                title = re.sub(r"^#{1,6}\s+", "", lines[start]).strip() or name
                # Include source and occurrence for repeated section headings.
                identity = f"{name}:{title.casefold()}"
                occurrences[identity] = occurrences.get(identity, 0) + 1
                section_id = "section_" + digest(f"{identity}:{occurrences[identity]}")[:16]
                sections.append({"id": section_id, "title": title, "source": f"context/{name}",
                                 "source_sha256": document["sha256"], "line_start": start + 1,
                                 "line_end": end, "content": entry})
    return {"schema_version": 1, "documents": documents, "achievements": achievements, "sections": sections}


def index(bundle: dict) -> dict:
    return {"ok": True, "schema_version": 1,
            "documents": [metadata(item) for item in bundle["documents"]],
            "achievements": [metadata(item) for item in bundle["achievements"]],
            "sections": [metadata(item) for item in bundle["sections"]],
            "counts": {key: len(bundle[key]) for key in ("documents", "achievements", "sections")}}


def read_record(bundle: dict, identity: str) -> dict:
    for kind in ("documents", "achievements", "sections"):
        for item in bundle[kind]:
            if item["id"] == identity or (kind == "documents" and identity in (item["path"], Path(item["path"]).name)):
                return {"ok": True, "schema_version": 1, "kind": kind[:-1], "record": item}
    raise ValueError("Unknown source or evidence ID. Run index to discover exact identifiers.")


def search(bundle: dict, query: str, limit: int = 5, kind: str = "all") -> dict:
    terms = list(dict.fromkeys(re.findall(r"[\w+#.-]+", query.casefold())))
    terms = [term for term in terms if any(character.isalnum() for character in term)]
    if not terms:
        raise ValueError("query must contain a search term")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    candidates = []
    if kind in ("all", "achievement"):
        candidates.extend(("achievement", item) for item in bundle["achievements"])
    if kind in ("all", "section"):
        candidates.extend(("section", item) for item in bundle["sections"])
    matches = []
    for record_kind, record in candidates:
        title = record["title"].casefold()
        tags = " ".join(record.get("tags", [])).casefold()
        content = record["content"].casefold()
        matched = [term for term in terms if term in content]
        if not matched:
            continue
        score = sum(8 * (term in title) + 4 * (term in tags) + (term in content) for term in terms)
        matches.append({"kind": record_kind, "score": score, "matched_terms": matched,
                        **metadata(record), "excerpt": record["content"][:3000],
                        "truncated": len(record["content"]) > 3000})
    matches.sort(key=lambda item: (-len(item["matched_terms"]), -item["score"], item["id"]))
    return {"ok": True, "schema_version": 1, "query": query, "total_matches": len(matches),
            "results": matches[:limit], "method": "Deterministic lexical matching; no model or semantic inference."}


def validate(bundle: dict) -> dict:
    return {"ok": True, "schema_version": 1, "counts": index(bundle)["counts"],
            "checks": ["Required sources exist and are nonempty UTF-8 text.",
                       "Brag entries have unique titles and source-linked IDs.",
                       "All referenced source hashes were computed from current local files."],
            "limits": ["Structure checks do not verify factual truth, completeness, or permission to share.",
                       "Review changes to personal context with the owner before publishing."]}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(json_text({"ok": False, "schema_version": 1, "error": {"code": "invalid_arguments", "message": message}}), end="")
        self.exit(2)


def main(argv=None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="List sources, sections and evidence IDs without full source text")
    command = commands.add_parser("search", help="Retrieve source-linked excerpts using lexical search")
    command.add_argument("--query", required=True)
    command.add_argument("--limit", type=int, default=5)
    command.add_argument("--kind", choices=("all", "achievement", "section"), default="all")
    command = commands.add_parser("read", help="Read an exact document, section or achievement discovered in index")
    command.add_argument("--id", required=True, help="Evidence ID, document ID, or an allowlisted context filename")
    commands.add_parser("export", help="Export all context as JSON; contains personal data")
    commands.add_parser("validate", help="Validate source structure and references without modifying files")
    args = parser.parse_args(argv)
    try:
        bundle = load_context(ROOT)
        if args.command == "index":
            result = index(bundle)
        elif args.command == "search":
            result = search(bundle, args.query, args.limit, args.kind)
        elif args.command == "read":
            result = read_record(bundle, args.id)
        elif args.command == "validate":
            result = validate(bundle)
        else:
            result = {"ok": True, **bundle, "privacy": "Contains personal data. Keep exports local and out of public commits/logs."}
        print(json_text(result), end="")
        return 0
    except (ValueError, OSError, UnicodeError, RuntimeError) as error:
        print(json_text({"ok": False, "schema_version": 1, "error": {"code": "invalid_context_or_request", "message": str(error)}}), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
