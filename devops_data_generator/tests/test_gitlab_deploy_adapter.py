"""Contract tests for the GitLab CD deploy adapter (GitLabDeployAdapter).

Covers: unified deployment schema field contract, GitLab deployment status →
status/conclusion mapping, run_id back-reference to the pipeline_run entity
id, the max_deployments_per_project cap, per-project failure isolation,
list_applications (environments), and multi-source merging in DeploymentTask.

Run from the repo root:

    python -m unittest devops_data_generator.tests.test_gitlab_deploy_adapter -v

No live GitLab and no python-gitlab SDK needed: projects/deployments are
SimpleNamespace fakes shaped like the python-gitlab objects, and the adapter
is built via __new__ (same pattern as test_gitlab_pipeline).
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.factory import create_deploy_adapter  # noqa: E402
from adapters.gitlab.deploy_adapter import GitLabDeployAdapter  # noqa: E402
from tasks.deployment_task import DeploymentTask  # noqa: E402


# --- fake python-gitlab object graph -----------------------------------------

_SHA_OK = "aaaabbbbccccdddd00001111222233334444"
_SHA_FAIL = "eeeeffff0000111122223333444455556666"


def _fake_project():
    deployments = [
        SimpleNamespace(
            id=501, iid=7, ref="main", sha=_SHA_OK, status="success",
            created_at="2026-09-01T06:00:00.000Z",
            updated_at="2026-09-01T06:03:00.000Z",
            user={"username": "root"},
            environment={"id": 11, "name": "production",
                         "external_url": "https://demo.example.com"},
            deployable={
                "id": 9001, "name": "deploy-prod", "stage": "deploy",
                "started_at": "2026-09-01T06:00:10.000Z",
                "finished_at": "2026-09-01T06:02:40.000Z",
                "duration": 150.0,
                "pipeline": {"id": 301, "sha": _SHA_OK, "ref": "main",
                             "status": "success"},
                "web_url": "http://gl/starops-demo/demo-app/-/jobs/9001",
            },
        ),
        SimpleNamespace(
            # deploy job deleted server-side → deployable=None must not crash
            id=500, iid=6, ref="main", sha=_SHA_FAIL, status="failed",
            created_at="2026-09-01T05:00:00.000Z",
            updated_at="2026-09-01T05:01:00.000Z",
            user=None,
            environment={"id": 10, "name": "staging"},
            deployable=None,
        ),
    ]
    environments = [
        SimpleNamespace(id=10, name="staging", slug="staging",
                        state="available", external_url=""),
        SimpleNamespace(id=11, name="production", slug="production",
                        state="available",
                        external_url="https://demo.example.com"),
    ]
    calls = []

    def _deployments_list(**kw):
        calls.append(kw)
        if "per_page" in kw:  # emulate first-page semantics
            return deployments[: kw["per_page"]]
        return deployments

    return SimpleNamespace(
        id=1, path_with_namespace="starops-demo/demo-app",
        web_url="http://gl/starops-demo/demo-app",
        deployments=SimpleNamespace(list=_deployments_list),
        environments=SimpleNamespace(list=lambda **kw: environments),
    ), calls


def _make_adapter():
    """GitLabDeployAdapter without __init__ (avoids SDK/client construction)."""
    project, calls = _fake_project()
    adapter = GitLabDeployAdapter.__new__(GitLabDeployAdapter)
    adapter.git = SimpleNamespace(
        _iter_projects=lambda: [project],
        validate_config=lambda: True,
    )
    adapter.max_deployments_per_project = 0
    return adapter, calls


class GitLabDeployAdapterContractTests(unittest.TestCase):
    """Adapter output must satisfy the IDeployAdapter contract."""

    DEPLOYMENT_FIELDS = {
        "deployment_id", "title", "description", "repository_id", "run_id",
        "environment_id", "commit_sha", "version", "status", "conclusion",
        "data_source", "platform_deployment_id", "url", "deployed_by",
        "release_id", "artifacts", "created_at", "started_at",
        "completed_at", "rollback_started_at", "rollback_completed_at",
        "duration_seconds",
    }

    def test_provider_name(self):
        adapter, _ = _make_adapter()
        self.assertEqual(adapter.get_provider_name(), "gitlab_cd")

    def test_factory_creates_gitlab_deploy_adapter(self):
        adapter = create_deploy_adapter(
            "gitlab", {"url": "http://gl", "access_token": "t"})
        self.assertIsInstance(adapter, GitLabDeployAdapter)

    def test_factory_still_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            create_deploy_adapter("jenkins", {})

    def test_validate_config_delegates_to_git_adapter(self):
        adapter, _ = _make_adapter()
        self.assertTrue(adapter.validate_config())
        adapter.git = SimpleNamespace(validate_config=lambda: False)
        self.assertFalse(adapter.validate_config())

    def test_list_deployments_contract_fields(self):
        adapter, _ = _make_adapter()
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 2)
        for rec in deployments:
            self.assertEqual(set(rec.keys()), self.DEPLOYMENT_FIELDS)
            self.assertEqual(rec["data_source"], "gitlab_cd")
            self.assertTrue(rec["deployment_id"].startswith("gitlab_cd:1:"))
            self.assertEqual(rec["repository_id"], "1")

    def test_success_deployment_mapping(self):
        adapter, _ = _make_adapter()
        rec = [d for d in adapter.list_deployments()
               if d["status"] == "success"][0]
        self.assertEqual(rec["deployment_id"], "gitlab_cd:1:501")
        self.assertEqual(rec["platform_deployment_id"], "501")
        self.assertEqual(rec["conclusion"], "success")
        self.assertEqual(rec["environment_id"], "production")
        self.assertEqual(rec["commit_sha"], _SHA_OK)
        self.assertEqual(rec["version"], _SHA_OK[:8])
        # run_id must match the pipeline_run entity id from
        # GitLabAdapter.list_pipeline_runs: gitlab_ci:{repo_id}:{pipeline_id}
        self.assertEqual(rec["run_id"], "gitlab_ci:1:301")
        self.assertEqual(rec["url"],
                         "http://gl/starops-demo/demo-app/-/jobs/9001")
        self.assertEqual(rec["deployed_by"], "gitlab:root")
        self.assertEqual(rec["created_at"], "2026-09-01T06:00:00.000Z")
        self.assertEqual(rec["started_at"], "2026-09-01T06:00:10.000Z")
        self.assertEqual(rec["completed_at"], "2026-09-01T06:02:40.000Z")
        self.assertEqual(rec["duration_seconds"], 150)

    def test_missing_deployable_degrades_to_empty_fields(self):
        adapter, _ = _make_adapter()
        rec = [d for d in adapter.list_deployments()
               if d["deployment_id"] == "gitlab_cd:1:500"][0]
        self.assertEqual((rec["status"], rec["conclusion"]),
                         ("failure", "failure"))
        self.assertEqual(rec["run_id"], "")
        self.assertEqual(rec["url"], "")
        self.assertEqual(rec["deployed_by"], "")
        self.assertEqual(rec["started_at"], "")
        self.assertEqual(rec["completed_at"], "")
        self.assertEqual(rec["duration_seconds"], 0)

    def test_status_mapping_matrix(self):
        adapter, _ = _make_adapter()
        cases = [
            ("created", "queued", ""),
            ("blocked", "queued", ""),
            ("running", "in_progress", ""),
            ("success", "success", "success"),
            ("failed", "failure", "failure"),
            ("canceled", "cancelled", ""),
            ("surprise-new-status", "queued", ""),
        ]
        for raw_status, want_status, want_conclusion in cases:
            with self.subTest(status=raw_status):
                dep = SimpleNamespace(
                    id=999, iid=9, ref="main", sha=_SHA_OK, status=raw_status,
                    created_at="", updated_at="", user=None,
                    environment=None, deployable=None)
                rec = adapter._map_deployment(
                    SimpleNamespace(path_with_namespace="g/p"), "1", dep)
                self.assertEqual(rec["status"], want_status)
                self.assertEqual(rec["conclusion"], want_conclusion)

    def test_max_deployments_per_project_caps_and_orders(self):
        adapter, calls = _make_adapter()
        adapter.max_deployments_per_project = 1
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 1)
        # newest first by id desc, single bounded page
        self.assertEqual(calls[-1]["order_by"], "id")
        self.assertEqual(calls[-1]["sort"], "desc")
        self.assertEqual(calls[-1]["per_page"], 1)

    def test_uncapped_fetches_all_pages(self):
        adapter, calls = _make_adapter()
        adapter.list_deployments()
        self.assertTrue(calls[-1].get("all"))

    def test_per_project_failure_isolated(self):
        adapter, _ = _make_adapter()
        good_project = adapter.git._iter_projects()[0]
        bad_project = SimpleNamespace(
            id=2, path_with_namespace="g/broken",
            deployments=SimpleNamespace(
                list=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))),
        )
        adapter.git = SimpleNamespace(
            _iter_projects=lambda: [bad_project, good_project],
            validate_config=lambda: True,
        )
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 2)  # all from the good project
        self.assertTrue(all(d["repository_id"] == "1" for d in deployments))

    def test_list_applications_maps_environments(self):
        adapter, _ = _make_adapter()
        apps = adapter.list_applications()
        self.assertEqual(len(apps), 2)
        prod = [a for a in apps if a["name"].endswith("/production")][0]
        self.assertEqual(prod["name"], "starops-demo/demo-app/production")
        self.assertEqual(prod["repo_url"], "http://gl/starops-demo/demo-app")
        self.assertEqual(prod["dest_server"], "https://demo.example.com")
        self.assertEqual(prod["health_status"], "available")


class _FakeDeployAdapter:
    """IDeployAdapter stand-in returning canned deployments."""

    def __init__(self, provider, deployments, raises=False):
        self._provider = provider
        self._deployments = deployments
        self._raises = raises

    def get_provider_name(self):
        return self._provider

    def validate_config(self):
        return True

    def list_deployments(self):
        if self._raises:
            raise RuntimeError(f"{self._provider} exploded")
        return list(self._deployments)

    def list_applications(self):
        return []


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


def _deployment(deployment_id, commit_sha=_SHA_OK):
    return {
        "deployment_id": deployment_id,
        "commit_sha": commit_sha,
        "version": commit_sha[:8],
        "status": "success",
        "conclusion": "success",
        "data_source": deployment_id.split(":", 1)[0],
    }


class DeploymentTaskMultiSourceTests(unittest.TestCase):
    def test_merges_multiple_deploy_adapters(self):
        task = DeploymentTask({}, [
            _FakeDeployAdapter("gitlab_cd", [_deployment("gitlab_cd:1:501")]),
            _FakeDeployAdapter("argocd", [_deployment("argocd:demo-app:3")]),
        ])
        task.set_shared_context(_FakeSharedContext())
        deployments = task.fetch_data()
        self.assertEqual(
            {d["deployment_id"] for d in deployments},
            {"gitlab_cd:1:501", "argocd:demo-app:3"},
        )

    def test_one_failing_source_does_not_sink_the_others(self):
        ctx = _FakeSharedContext()
        task = DeploymentTask({}, [
            _FakeDeployAdapter("broken", [], raises=True),
            _FakeDeployAdapter("gitlab_cd", [_deployment("gitlab_cd:1:501")]),
        ])
        task.set_shared_context(ctx)
        deployments = task.fetch_data()
        self.assertEqual(len(deployments), 1)
        self.assertIn("deployment_gitlab_cd:1:501", ctx._store)

    def test_validate_config_false_without_adapters(self):
        self.assertFalse(DeploymentTask({}, []).validate_config())

    def test_validate_config_requires_all_adapters_valid(self):
        good = _FakeDeployAdapter("gitlab_cd", [])
        bad = _FakeDeployAdapter("argocd", [])
        bad.validate_config = lambda: False
        self.assertFalse(DeploymentTask({}, [good, bad]).validate_config())
        self.assertTrue(DeploymentTask({}, [good]).validate_config())


if __name__ == "__main__":
    unittest.main()
