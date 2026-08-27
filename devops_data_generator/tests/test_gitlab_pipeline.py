"""Contract tests for GitLab CI pipeline support (C-1).

Covers: GitLab adapter list_pipelines/list_pipeline_runs mapping (mocked
python-gitlab objects, no SDK import needed), status/trigger mapping matrices,
the pipeline/pipeline_run entity tasks, and the two relationship tasks
(repository_contains_pipeline, pull_request_triggers_pipeline_run).

Run from repo root:
    python -m unittest devops_data_generator.tests.test_gitlab_pipeline -v
"""

import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.base import IGitAdapter  # noqa: E402
from adapters.gitlab.adapter import GitLabAdapter  # noqa: E402
from tasks.pipeline_task import PipelineTask  # noqa: E402
from tasks.pipeline_run_task import PipelineRunTask  # noqa: E402
from tasks.repository_contains_pipeline_task import RepositoryContainsPipelineTask  # noqa: E402
from tasks.pull_request_triggers_pipeline_run_task import (  # noqa: E402
    PullRequestTriggersPipelineRunTask,
)


# --- fake python-gitlab object graph -----------------------------------------

def _fake_project(jobs_enabled=True):
    pipelines = [
        SimpleNamespace(id=101, iid=5, sha="aaaabbbbccccdddd00001111222233334444",
                        ref="main", status="success", source="push",
                        web_url="http://gl/1/pipelines/101",
                        user={"username": "root"},
                        created_at="2026-08-27T01:00:00Z",
                        started_at="2026-08-27T01:00:05Z",
                        finished_at="2026-08-27T01:02:05Z",
                        duration=120.0, queued_duration=5.0),
        SimpleNamespace(id=102, iid=6, sha="eeeeffff0000111122223333444455556666",
                        ref="main", status="failed", source="merge_request_event",
                        web_url="http://gl/1/pipelines/102", user=None,
                        created_at="2026-08-27T02:00:00Z",
                        started_at=None, finished_at=None,
                        duration=None, queued_duration=None),
    ]
    return SimpleNamespace(
        id=1, path_with_namespace="starops-demo/demo-app",
        jobs_enabled=jobs_enabled, ci_config_path="",
        web_url="http://gl/starops-demo/demo-app",
        created_at="2026-01-01T00:00:00Z", last_activity_at="2026-08-27T02:00:00Z",
        pipelines=SimpleNamespace(list=lambda **kw: pipelines),
    )


def _make_adapter(jobs_enabled=True):
    """GitLabAdapter without __init__ (avoids SDK/client construction)."""
    adapter = GitLabAdapter.__new__(GitLabAdapter)
    project = _fake_project(jobs_enabled)
    adapter.client = SimpleNamespace(
        projects=SimpleNamespace(get=lambda _id: project))
    return adapter


class GitLabPipelineMappingTests(unittest.TestCase):
    def test_list_pipelines_definition_from_ci_config(self):
        pipes = _make_adapter().list_pipelines("1")
        self.assertEqual(len(pipes), 1)
        p = pipes[0]
        self.assertEqual(p["pipeline_id"], "gitlab:1:.gitlab-ci.yml")
        self.assertEqual(p["platform_pipeline_id"], "1:.gitlab-ci.yml")
        self.assertEqual(p["repository_id"], "1")
        self.assertEqual(p["data_source"], "gitlab")
        self.assertTrue(p["is_active"])
        self.assertTrue(p["url"].endswith("/-/pipelines"))

    def test_list_pipelines_skips_ci_disabled_project(self):
        self.assertEqual(_make_adapter(jobs_enabled=False).list_pipelines("1"), [])

    def test_list_pipeline_runs_mapping(self):
        runs = _make_adapter().list_pipeline_runs("1")
        self.assertEqual(len(runs), 2)
        ok, bad = runs
        self.assertEqual(ok["run_id"], "gitlab:1:101")
        self.assertEqual(ok["pipeline_id"], "gitlab:1:.gitlab-ci.yml")
        self.assertEqual(ok["commit_sha"], "aaaabbbbccccdddd00001111222233334444")
        self.assertEqual((ok["status"], ok["conclusion"]), ("success", "success"))
        self.assertEqual(ok["trigger_type"], "push")
        self.assertEqual(ok["triggered_by"], "gitlab:root")
        self.assertEqual(ok["duration_seconds"], 120)
        self.assertEqual(ok["queue_duration_seconds"], 5)
        self.assertEqual(bad["status"], "failure")
        self.assertEqual(bad["conclusion"], "failure")
        self.assertEqual(bad["trigger_type"], "pull_request")
        self.assertEqual(bad["duration_seconds"], 0)   # None → 0
        self.assertEqual(bad["started_at"], "")

    def test_status_and_source_matrices(self):
        self.assertEqual(GitLabAdapter._map_pipeline_status("running"), "in_progress")
        self.assertEqual(GitLabAdapter._map_pipeline_status("pending"), "queued")
        self.assertEqual(GitLabAdapter._map_pipeline_status("canceled"), "cancelled")
        self.assertEqual(GitLabAdapter._map_pipeline_status("skipped"), "skipped")
        self.assertEqual(GitLabAdapter._map_pipeline_status("unknown-x"), "queued")
        self.assertEqual(GitLabAdapter._map_pipeline_source("web"), "manual")
        self.assertEqual(GitLabAdapter._map_pipeline_source("schedule"), "schedule")
        self.assertEqual(GitLabAdapter._map_pipeline_conclusion("in_progress"), "")

    def test_base_adapter_default_methods_return_empty(self):
        """codeup 等未实现 CI 的 provider 走默认空实现，不炸。"""
        class Dummy(IGitAdapter):
            def list_repositories(self, fetch_details=True): return []
            def list_repository_members(self, repo_id): return []
            def list_repository_releases(self, repo_id): return []
            def get_release_by_tag(self, repo_id, tag): return None
            def list_pull_requests(self, repo_id): return []
            def get_provider_name(self): return "dummy"
            def get_default_branch_fallback(self): return "main"
            def validate_config(self): return True
        d = Dummy()
        self.assertEqual(d.list_pipelines("1"), [])
        self.assertEqual(d.list_pipeline_runs("1"), [])


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


class _FakeGitAdapter:
    def __init__(self, pipelines=None, runs=None):
        self._pipelines = pipelines or []
        self._runs = runs or []

    def get_provider_name(self):
        return "gitlab"

    def validate_config(self):
        return True

    def list_pipelines(self, repo_id):
        return list(self._pipelines)

    def list_pipeline_runs(self, repo_id):
        return list(self._runs)


REPO = {"repository_id": "1", "name": "demo-app"}
PIPE = {"pipeline_id": "gitlab:1:.gitlab-ci.yml", "repository_id": "1"}
RUN = {"run_id": "gitlab:1:101", "pipeline_id": "gitlab:1:.gitlab-ci.yml",
       "repository_id": "1", "commit_sha": "abc123", "status": "success"}


class PipelineTaskTests(unittest.TestCase):
    def _attach(self, task, initial=None):
        ctx = _FakeSharedContext()
        task.set_shared_context(ctx)
        for k, v in (initial or {}).items():
            ctx.set_data(k, v, "x", "seed")
        return ctx

    def test_pipeline_task_collects_and_shares(self):
        t = PipelineTask({}, _FakeGitAdapter(pipelines=[PIPE]))
        ctx = self._attach(t, {"repository_raw_data": [REPO]})
        out = t.fetch_data()
        self.assertEqual(out, [PIPE])
        self.assertEqual(ctx._store["pipeline_list"], [PIPE])

    def test_pipeline_task_empty_repos(self):
        t = PipelineTask({}, _FakeGitAdapter(pipelines=[PIPE]))
        self._attach(t)
        self.assertEqual(t.fetch_data(), [])

    def test_pipeline_run_task_collects(self):
        t = PipelineRunTask({}, _FakeGitAdapter(runs=[RUN]))
        ctx = self._attach(t, {"repository_raw_data": [REPO]})
        self.assertEqual(t.fetch_data(), [RUN])
        self.assertEqual(ctx._store["pipeline_run_list"], [RUN])

    def test_repository_contains_pipeline_edges(self):
        t = RepositoryContainsPipelineTask({})
        self._attach(t, {"pipeline_list": [PIPE]})
        rels = t.fetch_data()
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["__link_type__"], "contains")
        self.assertEqual(rels[0]["__src_entity_id__"], "1")
        self.assertEqual(rels[0]["__dest_entity_id__"], "gitlab:1:.gitlab-ci.yml")


class PullRequestTriggersPipelineRunTests(unittest.TestCase):
    def _run(self, prs, runs):
        t = PullRequestTriggersPipelineRunTask({})
        ctx = _FakeSharedContext()
        t.set_shared_context(ctx)
        ctx.set_data("pull_request_raw_data", prs, "raw_data", "pull_request")
        ctx.set_data("pipeline_run_list", runs, "pipeline_run", "pipeline_run")
        return t.fetch_data()

    def test_pr_id_primary_match(self):
        prs = [{"pr_id": "gitlab:1!3", "repository_id": "1"}]
        runs = [dict(RUN, pr_id="gitlab:1!3")]
        rels = self._run(prs, runs)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["__link_type__"], "triggers")
        self.assertEqual(rels[0]["__src_entity_id__"], "gitlab:1!3")
        self.assertEqual(rels[0]["__dest_entity_id__"], "gitlab:1:101")

    def test_commit_sha_fallback_match(self):
        prs = [{"pr_id": "gitlab:1!3", "repository_id": "1",
                "merge_commit_sha": "abc123", "source_commit_sha": "def456"}]
        rels = self._run(prs, [RUN])  # RUN.commit_sha == abc123
        self.assertEqual(len(rels), 1)

    def test_cross_repo_sha_no_match(self):
        prs = [{"pr_id": "gitlab:2!1", "repository_id": "2",
                "merge_commit_sha": "abc123", "source_commit_sha": ""}]
        self.assertEqual(self._run(prs, [RUN]), [])

    def test_no_match_no_edge(self):
        prs = [{"pr_id": "gitlab:1!3", "repository_id": "1",
                "merge_commit_sha": "zzz", "source_commit_sha": ""}]
        self.assertEqual(self._run(prs, [RUN]), [])

    def test_missing_inputs(self):
        self.assertEqual(self._run([], [RUN]), [])
        prs = [{"pr_id": "gitlab:1!3", "repository_id": "1", "merge_commit_sha": "abc123"}]
        self.assertEqual(self._run(prs, []), [])


if __name__ == "__main__":
    unittest.main()
