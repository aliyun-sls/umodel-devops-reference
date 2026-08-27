"""Contract tests for the Jenkins CI adapter and multi-source pipeline tasks.

Run from repo root:
    python -m unittest devops_data_generator.tests.test_jenkins_adapter -v
"""

import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.factory import create_ci_adapter  # noqa: E402
from adapters.jenkins import JenkinsAdapter  # noqa: E402
from tasks.pipeline_run_task import PipelineRunTask  # noqa: E402
from tasks.pipeline_task import PipelineTask  # noqa: E402


JOBS = {"jobs": [
    {"name": "demo-app-build", "url": "http://jenkins:8081/job/demo-app-build/",
     "buildable": True},
    {"name": "nightly-scan", "url": "http://jenkins:8081/job/nightly-scan/",
     "buildable": True},
]}

BUILDS = {
    "demo-app-build": {"builds": [
        {"number": 3, "result": "SUCCESS", "duration": 45000,
         "timestamp": 1787800000000, "url": "http://jenkins:8081/job/demo-app-build/3/",
         "building": False},
        {"number": 4, "result": None, "duration": 0,
         "timestamp": 1787800060000, "url": "http://jenkins:8081/job/demo-app-build/4/",
         "building": True},
    ]},
    "nightly-scan": {"builds": [
        {"number": 12, "result": "FAILURE", "duration": 30000,
         "timestamp": 1787700000000, "url": "http://jenkins:8081/job/nightly-scan/12/",
         "building": False},
    ]},
}


def _make_adapter(**overrides) -> JenkinsAdapter:
    config = {"url": "http://jenkins:8081", "user": "admin", "token": "t",
              "insecure": True,
              "repo_mapping": {"demo-app-build": "1"}}
    config.update(overrides)
    adapter = JenkinsAdapter(config)

    def fake_get(path: str):
        adapter._paths.append(path)
        if "/job/" in path:
            name = path.split("/job/")[1].split("/")[0]
            return BUILDS[name]
        return JOBS

    adapter._paths = []  # type: ignore[attr-defined]
    adapter._get = fake_get  # type: ignore[attr-defined]
    return adapter


class JenkinsAdapterContractTests(unittest.TestCase):
    def test_provider_name(self):
        self.assertEqual(_make_adapter().get_provider_name(), "jenkins")

    def test_factory(self):
        a = create_ci_adapter("jenkins", {"url": "http://x"})
        self.assertIsInstance(a, JenkinsAdapter)
        with self.assertRaises(ValueError):
            create_ci_adapter("travis", {})

    def test_list_pipelines_maps_jobs(self):
        pipes = _make_adapter().list_pipelines()
        self.assertEqual(len(pipes), 2)
        demo = pipes[0]
        self.assertEqual(demo["pipeline_id"], "jenkins:demo-app-build")
        self.assertEqual(demo["repository_id"], "1")       # repo_mapping 命中
        self.assertEqual(pipes[1]["repository_id"], "")    # 无映射则空
        self.assertEqual(demo["data_source"], "jenkins")
        self.assertTrue(demo["is_active"])

    def test_job_filter(self):
        pipes = _make_adapter(job_filter=["nightly-scan"]).list_pipelines()
        self.assertEqual([p["name"] for p in pipes], ["nightly-scan"])

    def test_list_pipeline_runs_status_mapping(self):
        runs = _make_adapter().list_pipeline_runs()
        self.assertEqual(len(runs), 3)
        by_id = {r["run_id"]: r for r in runs}
        ok = by_id["jenkins:demo-app-build:3"]
        self.assertEqual((ok["status"], ok["conclusion"]), ("success", "success"))
        self.assertEqual(ok["duration_seconds"], 45)
        self.assertEqual(ok["created_at"], "2026-08-27T03:06:40+00:00")
        building = by_id["jenkins:demo-app-build:4"]
        self.assertEqual((building["status"], building["conclusion"]),
                         ("in_progress", ""))
        self.assertEqual(building["completed_at"], "")
        bad = by_id["jenkins:nightly-scan:12"]
        self.assertEqual((bad["status"], bad["conclusion"]), ("failure", "failure"))

    def test_derive_status_matrix(self):
        cases = [
            (False, "SUCCESS", ("success", "success")),
            (False, "FAILURE", ("failure", "failure")),
            (False, "ABORTED", ("cancelled", "cancelled")),
            (False, "UNSTABLE", ("success", "")),
            (False, "NOT_BUILT", ("skipped", "")),
            (True, None, ("in_progress", "")),
            (False, None, ("queued", "")),
        ]
        for building, result, expected in cases:
            with self.subTest(building=building, result=result):
                self.assertEqual(
                    JenkinsAdapter._derive_status(building, result), expected)


class _FakeSharedContext:
    def __init__(self):
        self._store = {}

    def set_data(self, key, data, data_type, task_name):
        self._store[key] = data
        return True

    def get_data(self, key, default, task_name):
        return self._store.get(key, default)

    def has_data(self, key):
        return key in self._store

    def clear_expired(self):
        pass

    def get_execution_order(self, enabled):
        return enabled


class _FakeGit:
    def __init__(self, pipes=None, runs=None):
        self._p = pipes or []
        self._r = runs or []

    def get_provider_name(self):
        return "gitlab"

    def validate_config(self):
        return True

    def list_pipelines(self, repo_id):
        return list(self._p)

    def list_pipeline_runs(self, repo_id):
        return list(self._r)


class _FakeCI:
    def __init__(self, pipes=None, runs=None):
        self._p = pipes or []
        self._r = runs or []

    def get_provider_name(self):
        return "jenkins"

    def validate_config(self):
        return True

    def list_pipelines(self):
        return list(self._p)

    def list_pipeline_runs(self):
        return list(self._r)


class MultiSourceTaskTests(unittest.TestCase):
    def test_pipeline_task_merges_git_and_ci_sources(self):
        git = _FakeGit(pipes=[{"pipeline_id": "gitlab:1:.gitlab-ci.yml"}])
        ci = _FakeCI(pipes=[{"pipeline_id": "jenkins:demo-app-build"}])
        t = PipelineTask({}, git, [ci])
        ctx = _FakeSharedContext()
        t.set_shared_context(ctx)
        ctx.set_data("repository_raw_data", [{"repository_id": "1"}], "x", "seed")
        out = t.fetch_data()
        self.assertEqual({p["pipeline_id"] for p in out},
                         {"gitlab:1:.gitlab-ci.yml", "jenkins:demo-app-build"})

    def test_pipeline_run_task_merges(self):
        git = _FakeGit(runs=[{"run_id": "gitlab:1:101"}])
        ci = _FakeCI(runs=[{"run_id": "jenkins:demo-app-build:3"}])
        t = PipelineRunTask({}, git, [ci])
        ctx = _FakeSharedContext()
        t.set_shared_context(ctx)
        ctx.set_data("repository_raw_data", [{"repository_id": "1"}], "x", "seed")
        out = t.fetch_data()
        self.assertEqual({r["run_id"] for r in out},
                         {"gitlab:1:101", "jenkins:demo-app-build:3"})

    def test_no_ci_adapters_keeps_legacy_behavior(self):
        git = _FakeGit(pipes=[{"pipeline_id": "gitlab:1:.gitlab-ci.yml"}])
        t = PipelineTask({}, git)   # 不传 ci_adapters
        ctx = _FakeSharedContext()
        t.set_shared_context(ctx)
        ctx.set_data("repository_raw_data", [{"repository_id": "1"}], "x", "seed")
        out = t.fetch_data()
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
