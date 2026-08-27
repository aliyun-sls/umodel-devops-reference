"""Contract tests for the Argo CD deploy adapter and deployment tasks.

Run from the repo root:

    python -m unittest devops_data_generator.tests.test_argocd_adapter -v

No live Argo CD is needed: ``ArgoCDAdapter._get`` is replaced with a stub
serving canned REST responses, and the task tests use a fake adapter plus the
in-memory FakeSharedContext pattern from test_phase1_regressions.
"""

import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.argocd import ArgoCDAdapter  # noqa: E402
from adapters.factory import create_deploy_adapter  # noqa: E402
from tasks.deployment_task import DeploymentTask  # noqa: E402
from tasks.release_relates_to_deployment_task import (  # noqa: E402
    ReleaseRelatesToDeploymentTask,
)


# --- canned Argo CD REST payloads ------------------------------------------

APP_LIST = {
    "items": [
        {
            "metadata": {"name": "demo-app"},
            "spec": {
                "source": {"repoURL": "http://git.example.com/group/demo-app.git",
                           "targetRevision": "main"},
                "destination": {"server": "https://kubernetes.default.svc",
                                "namespace": "argocd-demo"},
            },
            "status": {"sync": {"status": "Synced"},
                       "health": {"status": "Healthy"}},
        },
        {
            "metadata": {"name": "broken-app"},
            "spec": {
                "source": {"repoURL": "http://git.example.com/group/broken.git",
                           "targetRevision": "main"},
                "destination": {"server": "https://kubernetes.default.svc",
                                "namespace": "default"},
            },
            "status": {"sync": {"status": "Synced"},
                       "health": {"status": "Degraded"}},
        },
    ]
}

APP_DETAIL = {
    "demo-app": {
        "spec": APP_LIST["items"][0]["spec"],
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
            "history": [
                {
                    "id": 3,
                    "revision": "96f2914c0000000000000000000000000000abcd",
                    "deployStartedAt": "2026-08-24T06:00:00Z",
                    "deployedAt": "2026-08-24T06:01:30Z",
                    "source": {"repoURL": "http://git.example.com/group/demo-app.git"},
                },
                {
                    # helm/oci-only entry: no git revision → must be skipped
                    "id": 2,
                    "revision": "",
                    "deployStartedAt": "2026-08-23T06:00:00Z",
                    "deployedAt": "2026-08-23T06:01:00Z",
                },
            ],
        },
    },
    "broken-app": {
        "spec": APP_LIST["items"][1]["spec"],
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Degraded"},
            "history": [
                {
                    "id": 7,
                    "revision": "aaaaaaaabbbbbbbbccccccccddddddddeeeeeeee",
                    "deployStartedAt": "2026-08-24T05:00:00Z",
                    "deployedAt": "2026-08-24T05:00:20Z",
                    "source": {"repoURL": "http://git.example.com/group/broken.git"},
                },
            ],
        },
    },
}


def _make_adapter(**overrides) -> ArgoCDAdapter:
    config = {
        "server": "http://argocd.example.com",
        "token": "t",
        "insecure": True,
        "repo_mapping": {
            "http://git.example.com/group/demo-app.git": "42",
            "http://git.example.com/group/broken.git": "43",
        },
    }
    config.update(overrides)
    adapter = ArgoCDAdapter(config)

    def fake_get(path: str):
        adapter._requested_paths.append(path)
        if path.startswith("/api/v1/applications/"):
            name = path.rsplit("/", 1)[-1]
            return APP_DETAIL[name]
        return APP_LIST

    adapter._requested_paths = []  # type: ignore[attr-defined]
    adapter._get = fake_get  # type: ignore[attr-defined]
    return adapter


class ArgoCDAdapterContractTests(unittest.TestCase):
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
        self.assertEqual(_make_adapter().get_provider_name(), "argocd")

    def test_validate_config_requires_server(self):
        self.assertFalse(ArgoCDAdapter({}).validate_config())

    def test_validate_config_calls_api(self):
        self.assertTrue(_make_adapter().validate_config())

    def test_factory_creates_argocd_adapter(self):
        adapter = create_deploy_adapter("argocd", {"server": "http://x"})
        self.assertIsInstance(adapter, ArgoCDAdapter)

    def test_factory_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            create_deploy_adapter("jenkins", {})

    def test_list_applications_maps_fields(self):
        apps = _make_adapter().list_applications()
        self.assertEqual(len(apps), 2)
        demo = apps[0]
        self.assertEqual(demo["name"], "demo-app")
        self.assertEqual(demo["repo_url"],
                         "http://git.example.com/group/demo-app.git")
        self.assertEqual(demo["sync_status"], "Synced")
        self.assertEqual(demo["health_status"], "Healthy")
        self.assertEqual(demo["dest_namespace"], "argocd-demo")

    def test_list_deployments_contract_fields(self):
        deployments = _make_adapter().list_deployments()
        # 2 git history entries (demo-app id=3, broken-app id=7);
        # the revision-less entry must be skipped.
        self.assertEqual(len(deployments), 2)
        for rec in deployments:
            self.assertEqual(set(rec.keys()), self.DEPLOYMENT_FIELDS)
            self.assertEqual(rec["data_source"], "argocd")
            self.assertTrue(rec["deployment_id"].startswith("argocd:"))
            self.assertTrue(rec["commit_sha"])

    def test_list_deployments_status_derivation(self):
        deployments = {d["environment_id"]: d
                       for d in _make_adapter().list_deployments()}
        demo = deployments["argocd-demo"]
        self.assertEqual(demo["deployment_id"], "argocd:demo-app:3")
        self.assertEqual((demo["status"], demo["conclusion"]),
                         ("success", "success"))
        self.assertEqual(demo["repository_id"], "42")
        self.assertEqual(demo["duration_seconds"], 90)
        self.assertEqual(demo["platform_deployment_id"], "3")
        self.assertEqual(demo["url"],
                         "http://argocd.example.com/applications/demo-app")

        broken = deployments["default"]
        self.assertEqual((broken["status"], broken["conclusion"]),
                         ("failure", "failure"))

    def test_app_filter_limits_applications(self):
        adapter = _make_adapter(app_filter=["demo-app"])
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 1)
        self.assertIn("demo-app", deployments[0]["deployment_id"])

    def test_no_fields_projection_in_requests(self):
        # Real Argo CD v3.5.1 silently drops metadata.name when a `fields`
        # projection is passed (gRPC field-mask semantics), which then makes
        # the per-app detail call hit /api/v1/applications/ → 403.
        # Contract: never rely on `fields`; fetch full objects.
        adapter = _make_adapter()
        adapter.validate_config()
        adapter.list_deployments()
        for path in adapter._requested_paths:
            self.assertNotIn("fields=", path)

    def test_skips_application_with_empty_name(self):
        adapter = _make_adapter()
        original = APP_LIST["items"]
        APP_LIST["items"] = original + [
            {"metadata": {}, "spec": {"source": {}, "destination": {}},
             "status": {}}
        ]
        try:
            apps = adapter.list_applications()
        finally:
            APP_LIST["items"] = original
        self.assertEqual([a["name"] for a in apps], ["demo-app", "broken-app"])

    def test_derive_status_matrix(self):
        cases = [
            ("Synced", "Healthy", ("success", "success")),
            ("OutOfSync", "Healthy", ("in_progress", "")),
            ("Synced", "Degraded", ("failure", "failure")),
            ("Synced", "Progressing", ("in_progress", "")),
            ("Synced", "Missing", ("failure", "failure")),
            ("Unknown", "Unknown", ("failure", "failure")),
        ]
        for sync, health, expected in cases:
            with self.subTest(sync=sync, health=health):
                self.assertEqual(
                    ArgoCDAdapter._derive_status(sync, health), expected)

    def test_duration_seconds_handles_missing_or_bad_input(self):
        self.assertEqual(ArgoCDAdapter._duration_seconds("", ""), 0)
        self.assertEqual(ArgoCDAdapter._duration_seconds("garbage", "also-bad"), 0)
        self.assertEqual(
            ArgoCDAdapter._duration_seconds("2026-08-24T00:00:00Z",
                                            "2026-08-24T00:02:00Z"),
            120,
        )


class _FakeDeployAdapter:
    """IDeployAdapter stand-in returning canned deployments."""

    def __init__(self, deployments):
        self._deployments = deployments

    def get_provider_name(self):
        return "argocd"

    def validate_config(self):
        return True

    def list_deployments(self):
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


def _deployment(commit_sha="96f2914c0000000000000000000000000000abcd",
                deployment_id="argocd:demo-app:3", version="96f2914c"):
    return {
        "deployment_id": deployment_id,
        "commit_sha": commit_sha,
        "version": version,
        "status": "success",
        "conclusion": "success",
        "data_source": "argocd",
    }


class DeploymentTaskTests(unittest.TestCase):
    def test_task_returns_adapter_records_and_shares_them(self):
        adapter = _FakeDeployAdapter([_deployment()])
        task = DeploymentTask({}, adapter)
        ctx = _FakeSharedContext()
        task.set_shared_context(ctx)

        deployments = task.fetch_data()
        self.assertEqual(len(deployments), 1)
        self.assertEqual(deployments[0]["deployment_id"], "argocd:demo-app:3")
        self.assertIn("deployment_argocd:demo-app:3", ctx._store)

    def test_task_name_is_deployment(self):
        # orchestrator stores raw results under "{task_name}_raw_data";
        # release_relates_to_deployment depends on "deployment_raw_data".
        self.assertEqual(DeploymentTask({}, _FakeDeployAdapter([])).task_name,
                         "deployment")


class ReleaseRelatesToDeploymentTaskTests(unittest.TestCase):
    def _run(self, releases, deployments):
        task = ReleaseRelatesToDeploymentTask({})
        ctx = _FakeSharedContext()
        task.set_shared_context(ctx)
        ctx.set_data("release_list", releases, "entity", "release")
        ctx.set_data("deployment_raw_data", deployments, "raw_data", "deployment")
        return task.fetch_data()

    def test_commit_sha_matches_target_commitish(self):
        rels = self._run(
            [{"release_id": "gitlab:42:v1.1.0",
              "tag_name": "v1.1.0",
              "target_commitish": "96f2914c0000000000000000000000000000abcd"}],
            [_deployment()],
        )
        self.assertEqual(len(rels), 1)
        rel = rels[0]
        self.assertEqual(rel["__link_type__"], "relates_to")
        self.assertEqual(rel["__src_entity_id__"], "gitlab:42:v1.1.0")
        self.assertEqual(rel["__dest_entity_id__"], "argocd:demo-app:3")

    def test_fallback_matches_version_against_tag_name(self):
        rels = self._run(
            [{"release_id": "gitlab:42:v9",
              "tag_name": "96f2914c",  # tag equals deployment version
              "target_commitish": "different-sha"}],
            [_deployment()],
        )
        self.assertEqual(len(rels), 1)

    def test_no_match_yields_no_edges(self):
        rels = self._run(
            [{"release_id": "gitlab:42:v1.0.0",
              "tag_name": "v1.0.0",
              "target_commitish": "0000aaaa"}],
            [_deployment()],
        )
        self.assertEqual(rels, [])

    def test_missing_inputs_yield_no_edges(self):
        self.assertEqual(self._run([], [_deployment()]), [])
        self.assertEqual(self._run([{"release_id": "x"}], []), [])


if __name__ == "__main__":
    unittest.main()
