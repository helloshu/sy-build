"""Check Android source selection without relying on live upstream state."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/resolve-android-ref.py"
spec = importlib.util.spec_from_file_location("android_ref", SCRIPT)
android_ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(android_ref)


class AndroidRefTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "android"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def commit(self, version, tag=None):
        (self.repo / "build.gradle").write_text(f'    siyuanVersionName = "{version}"\n')
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
             "commit", "-qm", version], cwd=self.repo, check=True,
        )
        if tag:
            subprocess.run(["git", "tag", "-a", tag, "-m", tag], cwd=self.repo, check=True,
                           env={**os.environ,
                                "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"})
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()

    def test_tag_wins_over_newer_default_branch(self):
        expected = self.commit("3.8.6", "v3.8.6")
        self.commit("3.8.7-alpha.1")
        self.assertEqual(android_ref.resolve("v3.8.6", str(self.repo)), expected)

    def test_untagged_matching_prerelease_resolves_to_commit(self):
        expected = self.commit("3.8.7-alpha.1")
        self.assertEqual(android_ref.resolve("v3.8.7-alpha.1", str(self.repo)), expected)

    def test_mismatched_default_branch_is_rejected(self):
        self.commit("3.8.7-alpha.2")
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            android_ref.resolve("v3.8.7-alpha.1", str(self.repo))

    def test_mislabeled_tag_is_rejected(self):
        self.commit("3.8.5", "v3.8.6")
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            android_ref.resolve("v3.8.6", str(self.repo))

    def test_remote_error_is_not_treated_as_missing_tag(self):
        with self.assertRaisesRegex(RuntimeError, "Cannot query Android tags"):
            android_ref.resolve("v3.8.6", str(self.repo / "missing"))


if __name__ == "__main__":
    unittest.main()
