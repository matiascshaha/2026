import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent.py"
spec = importlib.util.spec_from_file_location("agent", SCRIPT)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "context").mkdir()
        for name in agent.CONTEXT_FILES:
            (self.root / "context" / name).write_text("# Synthetic context\nExample only.\n")
        (self.root / "context/master_brag_sheet.md").write_text(
            "# Brag sheet\n\n## Achievement\n\nTitle: Built example tools\n\nContext: Professional Experience\nOrganization: Example Company\n\nImpact:\nMade work easier with Python.\n\nTags:\npython, tooling\n\n## Achievement\n\nTitle: Tested authentication\n\nContext: Personal Project\n\nAction:\nTested OAuth flows.\n")
        (self.root / "context/resume_base.md").write_text("# Resume\n\n## Identity\nName: Example Person\n\n## Skills\nPython, testing\n")

    def tearDown(self):
        self.temporary.cleanup()

    def test_index_contains_no_full_source_text(self):
        result = agent.index(agent.load_context(self.root))
        self.assertEqual(result["counts"]["documents"], 5)
        self.assertEqual(result["counts"]["achievements"], 2)
        for key in ("documents", "achievements", "sections"):
            self.assertTrue(all("content" not in item for item in result[key]))

    def test_stable_id_exact_source_lines_and_hash(self):
        result = agent.load_context(self.root)
        evidence = result["achievements"][0]
        self.assertEqual(evidence["line_start"], 3)
        self.assertEqual(evidence["source"], "context/master_brag_sheet.md")
        doc = result["documents"][0]
        self.assertEqual(doc["sha256"], agent.digest(doc["content"]))
        self.assertEqual(evidence["source_sha256"], doc["sha256"])
        self.assertEqual(evidence["content"], "\n".join(doc["content"].splitlines()[evidence["line_start"]-1:evidence["line_end"]]).strip())
        path = self.root / evidence["source"]
        path.write_text(path.read_text().replace("Made work easier", "Made work much easier"))
        self.assertEqual(agent.load_context(self.root)["achievements"][0]["id"], evidence["id"])

    def test_raw_crlf_bytes_are_preserved_and_hashed(self):
        content = b"# Preferences\r\n\r\nUse clear wording.\r\n"
        (self.root / "context/preferences.md").write_bytes(content)
        record = agent.read_record(agent.load_context(self.root), "preferences.md")["record"]
        self.assertEqual(record["content"].encode(), content)
        self.assertEqual(record["sha256"], agent.hashlib.sha256(content).hexdigest())

    def test_tags_and_professional_personal_context_preserved(self):
        entries = agent.load_context(self.root)["achievements"]
        self.assertEqual(entries[0]["tags"], ["python", "tooling"])
        self.assertEqual(entries[0]["organization"], "Example Company")
        self.assertEqual(entries[1]["context"], "Personal Project")
        self.assertIsNone(entries[1]["organization"])

    def test_duplicate_titles_fail_explicitly(self):
        path = self.root / "context/master_brag_sheet.md"
        path.write_text(path.read_text() * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate achievement"):
            agent.load_context(self.root)

    def test_missing_title_and_sections_fail(self):
        path = self.root / "context/master_brag_sheet.md"
        path.write_text("## Achievement\n\nImpact: Did something\n")
        with self.assertRaisesRegex(ValueError, "missing Title"):
            agent.load_context(self.root)
        path.write_text("# Brag sheet\nNo entries")
        with self.assertRaisesRegex(ValueError, "no '## Achievement'"):
            agent.load_context(self.root)

    def test_missing_empty_and_invalid_utf8_sources_fail(self):
        path = self.root / "context/preferences.md"
        path.write_text("  \n")
        with self.assertRaisesRegex(ValueError, "Empty context"):
            agent.load_context(self.root)
        path.write_bytes(b"\xff")
        with self.assertRaises(UnicodeDecodeError):
            agent.load_context(self.root)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            agent.load_context(self.root)

    def test_read_allows_only_known_source_or_evidence_ids(self):
        bundle = agent.load_context(self.root)
        for identity in ("resume_base.md", "context/resume_base.md", "document_resume_base"):
            self.assertIn("Example Person", agent.read_record(bundle, identity)["record"]["content"])
        evidence = bundle["achievements"][0]
        self.assertEqual(agent.read_record(bundle, evidence["id"])["record"], evidence)
        for identity in ("../../etc/passwd", "/etc/passwd", "unknown"):
            with self.assertRaisesRegex(ValueError, "Unknown source"):
                agent.read_record(bundle, identity)

    def test_context_symlink_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.md"
            external.write_text("private")
            path = self.root / "context/preferences.md"
            path.unlink()
            path.symlink_to(external)
            with self.assertRaisesRegex(ValueError, "escapes repository"):
                agent.load_context(self.root)

    def test_cyclic_source_symlink_error_is_structured_json(self):
        script = self.root / "scripts/agent.py"
        script.parent.mkdir()
        script.write_bytes(SCRIPT.read_bytes())
        path = self.root / "context/master_brag_sheet.md"
        path.unlink()
        path.symlink_to(path.name)
        result = subprocess.run([sys.executable, str(script), "index"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertEqual(json.loads(result.stdout)["schema_version"], 1)
        self.assertEqual(result.stderr, "")

    def test_search_ranks_matches_and_preserves_source_refs(self):
        bundle = agent.load_context(self.root)
        result = agent.search(bundle, "authentication OAuth", 1)
        self.assertEqual(result["results"][0]["title"], "Tested authentication")
        self.assertEqual(result["results"][0]["matched_terms"], ["authentication", "oauth"])
        self.assertIn("source_sha256", result["results"][0])
        self.assertEqual(agent.search(bundle, "no_such_term")["results"], [])

    def test_search_kind_and_limit(self):
        bundle = agent.load_context(self.root)
        result = agent.search(bundle, "Python", 50, "section")
        self.assertTrue(result["results"])
        self.assertTrue(all(item["kind"] == "section" for item in result["results"]))
        for limit in (0, 51):
            with self.assertRaises(ValueError):
                agent.search(bundle, "python", limit)
        with self.assertRaises(ValueError):
            agent.search(bundle, "?!")

    def test_excerpt_is_bounded_and_full_read_remains_available(self):
        path = self.root / "context/master_brag_sheet.md"
        path.write_text(path.read_text() + "OAuth detail. " * 1000)
        bundle = agent.load_context(self.root)
        hit = agent.search(bundle, "OAuth", 1)["results"][0]
        self.assertTrue(hit["truncated"])
        self.assertEqual(len(hit["excerpt"]), 3000)
        self.assertGreater(len(agent.read_record(bundle, hit["id"])["record"]["content"]), 3000)

    def test_validation_states_its_limits(self):
        result = agent.validate(agent.load_context(self.root))
        self.assertTrue(result["ok"])
        self.assertIn("factual truth", result["limits"][0])

    def test_cli_outputs_json_and_does_not_write_files(self):
        script = self.root / "scripts/agent.py"
        script.parent.mkdir()
        script.write_bytes(SCRIPT.read_bytes())
        before = sorted(str(path) for path in self.root.rglob("*"))
        for args in (["index"], ["search", "--query", "python"], ["read", "--id", "resume_base.md"], ["export"], ["validate"]):
            completed = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertEqual(before, sorted(str(path) for path in self.root.rglob("*")))

    def test_cli_usage_and_missing_source_errors_are_json(self):
        script = self.root / "scripts/agent.py"
        script.parent.mkdir()
        script.write_bytes(SCRIPT.read_bytes())
        for args in (["search"], ["read", "--id", "unknown"], ["nonexistent"]):
            result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(json.loads(result.stdout)["ok"])
            self.assertEqual(json.loads(result.stdout)["schema_version"], 1)
        (self.root / "context/preferences.md").unlink()
        result = subprocess.run([sys.executable, str(script), "index"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
