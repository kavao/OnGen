import tempfile
import unittest
from pathlib import Path

from tools.kernel.verify_doc_links import collect_markdown_files, run_check


ROOT = Path(__file__).resolve().parents[1]


class CollectMarkdownFilesTests(unittest.TestCase):
    def test_missing_input_path_is_reported(self) -> None:
        missing = ROOT / "DOES_NOT_EXIST"
        files, errors = collect_markdown_files([missing], ROOT)
        self.assertEqual(files, [])
        self.assertEqual(errors, [f"input path does not exist: {missing}"])

    def test_non_markdown_file_is_reported(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            files, errors = collect_markdown_files([path], ROOT)
            self.assertEqual(files, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("not a Markdown file", errors[0])
        finally:
            path.unlink(missing_ok=True)

    def test_existing_markdown_directory_is_collected(self) -> None:
        files, errors = collect_markdown_files([ROOT / "docs"], ROOT)
        self.assertGreater(len(files), 0)
        self.assertEqual(errors, [])


class RunCheckTests(unittest.TestCase):
    def test_missing_input_returns_error_exit_code(self) -> None:
        exit_code, errors, file_count = run_check([ROOT / "DOES_NOT_EXIST"], ROOT)
        self.assertEqual(exit_code, 1)
        self.assertEqual(file_count, 0)
        self.assertTrue(any("does not exist" in error for error in errors))
        self.assertTrue(any("no Markdown files to verify" in error for error in errors))

    def test_valid_docs_tree_passes(self) -> None:
        exit_code, errors, file_count = run_check([ROOT / "README.md", ROOT / "docs"], ROOT)
        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])
        self.assertGreater(file_count, 0)

    def test_broken_link_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            md = root / "broken.md"
            md.write_text("[missing](missing.md)\n", encoding="utf-8")
            exit_code, errors, file_count = run_check([md], root)
            self.assertEqual(exit_code, 1)
            self.assertEqual(file_count, 1)
            self.assertTrue(any("broken link" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
