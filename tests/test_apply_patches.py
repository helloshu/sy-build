"""Exercise patch selection against small, real Git repositories."""
import difflib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply-patches.sh"


class PatchSelectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.patches = self.root / "patches"
        self.patches.mkdir()
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)

    def patch(self, name, before, after, filename="code.txt"):
        path = self.patches / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile="a/" + filename, tofile="b/" + filename,
        )))

    def run_patches(self):
        # The patch directory must resolve relative to the caller, not the source.
        return subprocess.run(
            [os.environ.get("TEST_BASH", "bash"), str(SCRIPT), str(self.source), "patches"],
            cwd=self.root, text=True, capture_output=True,
        )

    def test_unknown_tag_falls_back_and_repeat_is_unchanged(self):
        original = "start\nnew upstream\nend\n"
        expected = "start\npatched\nend\n"
        target = self.source / "code.txt"
        target.write_text(original)
        self.patch("fix.patch", "start\nold upstream\nend\n", expected)
        self.patch("versions/v3.8.5/fix.patch", original, expected)
        first = self.run_patches()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("versions/v3.8.5/fix.patch", first.stdout)
        self.assertEqual(target.read_text(), expected)
        second = self.run_patches()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(target.read_text(), expected)
        self.assertIn("新应用 0，已应用 1", second.stdout)

    def tag_source(self, tag):
        subprocess.run(["git", "add", "."], cwd=self.source, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
             "commit", "-qm", "fixture"], cwd=self.source, check=True,
        )
        subprocess.run(["git", "tag", tag], cwd=self.source, check=True)

    def test_exact_tag_precedes_other_strict_candidates(self):
        original = "start\nvalue\nend\n"
        target = self.source / "code.txt"
        target.write_text(original)
        self.tag_source("v2")
        self.patch("fix.patch", original, original.replace("value", "default"))
        self.patch("versions/v2/fix.patch", original, original.replace("value", "exact"))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), original.replace("value", "exact"))

    def test_prerelease_without_directory_uses_compatible_candidate(self):
        original = "start\nnew upstream\nend\n"
        target = self.source / "code.txt"
        target.write_text(original)
        self.tag_source("v3.8.7-alpha.1")
        self.patch("fix.patch", original.replace("new upstream", "old upstream"),
                   original.replace("new upstream", "patched"))
        self.patch("versions/v3.8.5/fix.patch", original, original.replace("new upstream", "patched"))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), original.replace("new upstream", "patched"))

    def test_already_applied_candidate_precedes_applicable_default(self):
        original = "start\npatched\nend\n"
        target = self.source / "code.txt"
        target.write_text(original)
        self.patch("fix.patch", original, original.replace("patched", "double patch"))
        self.patch("versions/v1/fix.patch", original.replace("patched", "upstream"), original)
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), original)

    def test_empty_patch_directory_fails(self):
        result = self.run_patches()
        self.assertNotEqual(result.returncode, 0)

    def test_strict_alternative_precedes_relaxed_default(self):
        original = "new context\nnear\nvalue\nend\n"
        target = self.source / "code.txt"
        target.write_text(original)
        self.patch("fix.patch", original.replace("new context", "old context"),
                   original.replace("new context", "old context").replace("value", "wrong"))
        self.patch("versions/v1/fix.patch", original, original.replace("value", "correct"))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("strict, versions/v1/fix.patch", result.stdout)
        self.assertIn("correct", target.read_text())

    def test_incompatible_patch_stops_before_later_patch(self):
        target = self.source / "code.txt"
        original = "start\nunknown\nend\n"
        target.write_text(original)
        self.patch("01-required.patch", "start\nold\nend\n", "start\npatched\nend\n")
        self.patch("02-later.patch", original, original.replace("unknown", "later"))
        result = self.run_patches()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("01-required.patch", result.stderr)
        self.assertEqual(target.read_text(), original)

    def test_insertion_requires_context(self):
        target = self.source / "code.txt"
        target.write_text("unrelated\n")
        self.patch("fix.patch", "start\nend\n", "start\ninsert\nend\n")
        result = self.run_patches()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "unrelated\n")

    def test_failed_candidate_does_not_partially_modify_tree(self):
        original = "start\nvalue\nend\n"
        (self.source / "code.txt").write_text(original)
        self.patch("fix.patch", original, original.replace("value", "wrong"))
        self.patch("missing.patch", original, original.replace("value", "missing"), "missing.txt")
        missing = self.patches / "missing.patch"
        first = self.patches / "fix.patch"
        first.write_text(first.read_text() + missing.read_text())
        missing.unlink()
        self.patch("versions/v1/fix.patch", original, original.replace("value", "correct"))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.source / "code.txt").read_text(), original.replace("value", "correct"))
        self.assertFalse((self.source / "missing.txt").exists())


if __name__ == "__main__":
    unittest.main()
