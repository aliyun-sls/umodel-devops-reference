"""Contract tests for release field shaping and the stdout logging mode.

Covers:
- ReleaseTask emits ``commit_sha`` (passthrough from the git adapter) and
  fills both ``created_at`` and ``published_at`` from the adapter's unified
  ``release_time`` — the schema/data-mapping fields these feed must not go
  empty again.
- ``setup_logging`` with ``file: "stdout"`` attaches no FileHandler (no log
  file is created on disk), while the default/empty value keeps the legacy
  file behaviour.

Run from the repo root:

    python -m unittest devops_data_generator.tests.test_release_fields -v

Fixtures are synthetic; no network access.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent  # devops_data_generator/
sys.path.insert(0, str(_PKG))

from tasks.release_task import ReleaseTask  # noqa: E402


class _StubContext:
    def __init__(self, repositories):
        self._data = {"repository_raw_data": repositories}

    def get_data(self, key, default=None, task_name=None):
        return self._data.get(key, default)

    def set_data(self, key, data, data_type="unknown", task_name=None):
        self._data[key] = data
        return True


class _StubGitAdapter:
    def __init__(self, releases):
        self._releases = releases

    def get_provider_name(self):
        return "github"

    def validate_config(self):
        return True

    def list_repository_releases(self, repository_id):
        return self._releases


class ReleaseShapingTest(unittest.TestCase):
    def _run_task(self, raw_releases):
        adapter = _StubGitAdapter(raw_releases)
        task = ReleaseTask({}, adapter)
        task.set_shared_context(
            _StubContext([{"repository_id": 4242, "name": "demo-app"}])
        )
        return task.fetch_data()

    def test_commit_sha_and_published_at_are_emitted(self):
        shaped = self._run_task(
            [
                {
                    "release_id": "gh-rel-1",
                    "tag_name": "v1.2.3",
                    "release_time": "2026-09-01T08:00:00Z",
                    "commit_sha": "deadbeef" * 5,
                }
            ]
        )
        self.assertEqual(len(shaped), 1)
        release = shaped[0]
        self.assertEqual(release["commit_sha"], "deadbeef" * 5)
        self.assertEqual(release["published_at"], "2026-09-01T08:00:00Z")
        self.assertEqual(release["created_at"], "2026-09-01T08:00:00Z")

    def test_missing_fields_default_to_empty_string(self):
        shaped = self._run_task([{"tag_name": "v0.1.0"}])
        self.assertEqual(len(shaped), 1)
        release = shaped[0]
        self.assertEqual(release["commit_sha"], "")
        self.assertEqual(release["published_at"], "")
        self.assertEqual(release["created_at"], "")


class StdoutLoggingTest(unittest.TestCase):
    """Run setup_logging in a subprocess: logging.basicConfig is process-global."""

    def _run_setup(self, snippet, cwd):
        code = (
            "import sys; sys.path.insert(0, {pkg!r});"
            "import main;"
            "main.setup_logging({snippet});"
            "import logging; logging.warning('MARKER-OUTPUT');"
        ).format(pkg=str(_PKG), snippet=snippet)
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )

    def test_stdout_mode_creates_no_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_setup("{'file': 'stdout'}", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MARKER-OUTPUT", result.stderr + result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [])  # nothing written to cwd

    def test_empty_file_falls_back_to_default_path(self):
        # PR #11 back-compat: explicit file: "" must still land on the default
        # log file instead of crashing with IsADirectoryError.
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_setup("{'file': ''}", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            default_log = Path(tmp) / "logs" / "devops_data_generator.log"
            self.assertTrue(default_log.exists())


if __name__ == "__main__":
    unittest.main()
