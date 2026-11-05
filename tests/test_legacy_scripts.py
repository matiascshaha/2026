"""Legacy shell safety regressions; all application data is synthetic."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class LegacyScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="legacy workflow ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("scripts", "pdf_gen", "templates", "context", "intake", "bin"):
            (self.root / directory).mkdir()
        for script in ("prepare_application.sh", "generate_application_answers.sh", "export_pdfs.sh"):
            shutil.copy2(REPO / "scripts" / script, self.root / "scripts" / script)
        shutil.copy2(REPO / "pdf_gen/common.sh", self.root / "pdf_gen/common.sh")
        (self.root / "templates/pdf_compact.css").write_text("body {}")
        for name in ("master_brag_sheet", "resume_base", "preferences", "resume_quality_guide", "profile_links"):
            (self.root / "context" / (name + ".md")).write_text("# Synthetic fixture\nExample only.\n")
        (self.root / "intake/job_description.txt").write_text("Synthetic role\n\n")
        (self.root / "intake/application_questions.txt").write_text("Example question?\n")
        self.job = self.root / "jobs/acme"
        self.env = dict(os.environ, PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"])
        self.mock("wkhtmltopdf", "exit 0")
        self.mock("mdls", "exit 1")
        self.mock("pdfinfo", 'printf "Pages: %s\\n" "${MOCK_PAGES:-1}"')
        self.mock("pandoc", '''
input="$1"
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then output="$2"; shift 2; else shift; fi
done
if [ "${MOCK_FAIL_COVER:-0}" = 1 ] && [[ "$input" == *_cover_letter.md ]]; then exit 9; fi
if [ "${MOCK_EMPTY:-0}" = 1 ]; then : > "$output"; else printf '%%PDF-1.4\\nsynthetic\\n' > "$output"; fi
''')

    def mock(self, name, body):
        path = self.root / "bin" / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body + "\n")
        path.chmod(0o755)

    def run_script(self, script, *args, **env):
        return subprocess.run(["bash", str(self.root / "scripts" / script), *args],
                              cwd=self.root, env=dict(self.env, **env),
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def prepare(self, *args):
        result = self.run_script("prepare_application.sh", "--company", "Acme", *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def documents(self):
        self.prepare()
        for name in ("resume", "cover_letter"):
            (self.job / f"acme_{name}.md").write_text("# Example Candidate\nReal synthetic body text.\n")
            (self.job / "pdf" / f"acme_{name}.pdf").write_bytes(b"old validated PDF")

    def assert_old_pdfs(self):
        for name in ("resume", "cover_letter"):
            self.assertEqual((self.job / "pdf" / f"acme_{name}.pdf").read_bytes(), b"old validated PDF")
        self.assertEqual(list((self.job / "pdf").glob(".export.*")), [])

    def test_prepare_is_portable_and_preserves_custom_questions(self):
        self.prepare()
        self.assertEqual((self.job / "job_description.txt").read_text(), "Synthetic role\n")
        (self.job / "application_questions.txt").write_text("Custom local question?\n")
        self.prepare()
        self.assertEqual((self.job / "application_questions.txt").read_text(), "Custom local question?\n")

    def test_snapshots_are_unique_even_with_identical_timestamp(self):
        self.prepare()
        self.mock("date", "echo 20260101_000000")
        self.prepare("--snapshot")
        self.prepare("--snapshot")
        snapshots = list((self.job / "history").iterdir())
        self.assertEqual(len(snapshots), 2)
        self.assertTrue(all((p / "acme_resume.md").exists() for p in snapshots))

    def test_empty_slug_is_rejected(self):
        result = self.run_script("prepare_application.sh", "--company", "!!!")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "jobs").exists())

    def test_raw_path_slugs_are_rejected(self):
        for script in ("export_pdfs.sh", "generate_application_answers.sh"):
            for slug in ("../outside", "/tmp/outside", "acme/../../outside", "UPPER"):
                with self.subTest(script=script, slug=slug):
                    self.assertNotEqual(self.run_script(script, "--company", slug).returncode, 0)

    def test_symlinked_workspace_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "jobs").mkdir()
        self.job.symlink_to(outside, target_is_directory=True)
        for script in ("prepare_application.sh", "export_pdfs.sh", "generate_application_answers.sh"):
            self.assertNotEqual(self.run_script(script, "--company", "acme").returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_mutable_file_is_rejected(self):
        self.prepare()
        outside = self.root / "outside.txt"
        outside.write_text("Preserve me")
        questions = self.job / "application_questions.txt"
        questions.unlink()
        questions.symlink_to(outside)
        self.assertNotEqual(self.run_script("prepare_application.sh", "--company", "acme").returncode, 0)
        self.assertEqual(outside.read_text(), "Preserve me")

    def test_missing_or_placeholder_document_rejects_entire_export(self):
        self.documents()
        cover = self.job / "acme_cover_letter.md"
        for content in (None, "# acme_cover_letter\n", "# Cover letter\nTODO: write letter\n"):
            with self.subTest(content=content):
                if content is None:
                    cover.unlink()
                else:
                    cover.write_text(content)
                result = self.run_script("export_pdfs.sh", "--company", "acme")
                self.assertNotEqual(result.returncode, 0)
                self.assert_old_pdfs()

    def test_converter_failure_preserves_both_previous_pdfs(self):
        self.documents()
        result = self.run_script("export_pdfs.sh", "--company", "acme", MOCK_FAIL_COVER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_pdfs()

    def test_invalid_pages_preserve_previous_pdfs(self):
        self.documents()
        for pages in ("0", "2", "unknown"):
            with self.subTest(pages=pages):
                result = self.run_script("export_pdfs.sh", "--company", "acme", MOCK_PAGES=pages)
                self.assertNotEqual(result.returncode, 0)
                self.assert_old_pdfs()

    def test_empty_pdf_is_rejected_even_without_page_check(self):
        self.documents()
        result = self.run_script("export_pdfs.sh", "--company", "acme", "--no-page-check", MOCK_EMPTY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_pdfs()

    def test_symlinked_pdf_directory_is_rejected(self):
        self.prepare()
        outside = self.root / "outside-pdf"
        outside.mkdir()
        (self.job / "pdf").rmdir()
        (self.job / "pdf").symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_script("export_pdfs.sh", "--company", "acme").returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_pdf_destination_directory_is_rejected(self):
        self.documents()
        destination = self.job / "pdf/acme_cover_letter.pdf"
        destination.unlink()
        destination.mkdir()
        result = self.run_script("export_pdfs.sh", "--company", "acme")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.job / "pdf/acme_resume.pdf").read_bytes(), b"old validated PDF")
        self.assertEqual(list(destination.iterdir()), [])

    def test_success_publishes_both_pdfs_and_removes_staging(self):
        self.documents()
        result = self.run_script("export_pdfs.sh", "--company", "acme")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("resume", "cover_letter"):
            self.assertTrue((self.job / "pdf" / f"acme_{name}.pdf").read_bytes().startswith(b"%PDF-"))
        self.assertEqual(list((self.job / "pdf").glob(".export.*")), [])


if __name__ == "__main__":
    unittest.main()
