"""Contract tests for the GitHub adapters (git provider + GitHub Actions CI).

Covers: repo scope resolution (explicit/org/user, dedupe, unreadable-repo
tolerance), pagination, unified field contracts for repositories/members/
releases/pull_requests, role mapping, tag→commit resolution, workflow/run
mapping (status/conclusion/event matrices, pr_id backfill, durations), and
multi-failure isolation.

Run from the repo root:

    python -m unittest devops_data_generator.tests.test_github_adapter -v

All fixtures are synthetic (octo-org/demo-app); no real org names, tokens,
or ids. No network access: HTTP is replaced with a stub client.
"""

import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent          # devops_data_generator/
sys.path.insert(0, str(_PKG))

from adapters.factory import (  # noqa: E402
    create_ci_adapter, create_deploy_adapter, create_git_adapter,
)
from adapters.github.adapter import GitHubAdapter  # noqa: E402
from adapters.github.actions_adapter import GitHubActionsAdapter  # noqa: E402
from adapters.github.client import GitHubClient, resolve_repos  # noqa: E402
from adapters.github.deploy_adapter import GitHubDeployAdapter  # noqa: E402


# --- synthetic fixtures ------------------------------------------------------

REPO = {
    "id": 9001,
    "full_name": "octo-org/demo-app",
    "description": "synthetic demo repo",
    "default_branch": "main",
    "language": "Python",
    "visibility": "public",
    "html_url": "https://gh.example.com/octo-org/demo-app",
    "created_at": "2026-01-01T00:00:00Z",
    "pushed_at": "2026-09-01T00:00:00Z",
    "owner": {"id": 777, "login": "octo-org"},
}

MEMBERS = [
    {"id": 101, "login": "alice", "role_name": "admin",
     "avatar_url": "https://gh.example.com/a.png"},
    {"id": 102, "login": "bob", "role_name": "write", "avatar_url": ""},
    {"id": 103, "login": "carol", "role_name": "read", "avatar_url": ""},
]

RELEASES = [
    {"tag_name": "v1.2.0", "name": "v1.2.0", "target_commitish": "main",
     "draft": False, "html_url": "https://gh.example.com/releases/v1.2.0",
     "author": {"login": "alice"}, "published_at": "2026-08-01T00:00:00Z",
     "body": "release notes"},
]

PULLS = [
    {"number": 42, "title": "Add feature", "body": "desc", "state": "closed",
     "merged_at": "2026-08-02T00:00:00Z", "closed_at": "2026-08-02T00:00:00Z",
     "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-02T00:00:00Z",
     "user": {"id": 101}, "requested_reviewers": [{"id": 102}],
     "head": {"ref": "feat-x", "sha": "headsha111"},
     "base": {"ref": "main"}, "merge_commit_sha": "mergesha222",
     "html_url": "https://gh.example.com/pull/42"},
]

WORKFLOWS = {"total_count": 1, "workflows": [
    {"id": 501, "name": "verify", "path": ".github/workflows/verify.yml",
     "state": "active", "html_url": "https://gh.example.com/actions/verify",
     "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z"},
]}

RUNS = {"total_count": 2, "workflow_runs": [
    {"id": 7001, "run_number": 9, "event": "push", "status": "completed",
     "conclusion": "success", "head_sha": "aaaabbbbccccdddd00001111222233334444",
     "head_branch": "main", "actor": {"id": 101},
     "html_url": "https://gh.example.com/actions/runs/7001",
     "created_at": "2026-09-01T06:00:00Z",
     "run_started_at": "2026-09-01T06:00:30Z",
     "updated_at": "2026-09-01T06:02:30Z", "pull_requests": []},
    {"id": 7000, "run_number": 8, "event": "pull_request", "status": "completed",
     "conclusion": "failure", "head_sha": "eeeeffff0000111122223333444455556666",
     "head_branch": "feat-x", "actor": {"id": 102},
     "html_url": "https://gh.example.com/actions/runs/7000",
     "created_at": "2026-08-31T06:00:00Z",
     "run_started_at": "2026-08-31T06:00:10Z",
     "updated_at": "2026-08-31T06:01:40Z", "pull_requests": [{"number": 42}]},
]}


class FakeClient:
    """GitHubClient stand-in serving canned payloads keyed by path."""

    def __init__(self, responses=None, paginated=None):
        self.responses = responses or {}
        self.paginated_responses = paginated or {}
        self.get_calls = []

    def get(self, path, params=None):
        self.get_calls.append((path, params))
        payload = self.responses[path]
        if isinstance(payload, Exception):
            raise payload
        return payload

    def get_paginated(self, path, params=None, wrapper="", max_pages=0):
        payload = self.paginated_responses[path]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _make_git_adapter(client):
    """GitHubAdapter without __init__ (no network), scope pre-resolved."""
    adapter = GitHubAdapter.__new__(GitHubAdapter)
    adapter.client = client
    adapter.token = "t"
    adapter.fetch_details = True
    adapter._config = {}
    adapter._repos = [("octo-org/demo-app", "9001", REPO)]
    adapter._tag_sha_cache = {}
    return adapter


def _make_actions_adapter(client, max_runs=20):
    adapter = GitHubActionsAdapter.__new__(GitHubActionsAdapter)
    adapter.client = client
    adapter._config = {}
    adapter._repos = [("octo-org/demo-app", "9001", REPO)]
    adapter.max_runs_per_workflow = max_runs
    return adapter


def _make_deploy_adapter(client, max_per=20):
    adapter = GitHubDeployAdapter.__new__(GitHubDeployAdapter)
    adapter.client = client
    adapter._config = {}
    adapter._repos = [("octo-org/demo-app", "9001", REPO)]
    adapter.max_deployments_per_project = max_per
    return adapter


DEPLOYMENTS = [
    {"id": 8001, "sha": "aaaabbbbccccdddd00001111222233334444", "ref": "main",
     "task": "deploy", "environment": "production", "description": None,
     "creator": {"id": 101, "login": "alice"},
     "created_at": "2026-09-01T06:00:00Z", "updated_at": "2026-09-01T06:02:40Z"},
    {"id": 8000, "sha": "eeeeffff0000111122223333444455556666", "ref": "main",
     "task": "deploy", "environment": "staging", "description": "deploy to staging",
     "creator": {"id": 102, "login": "bob"},
     "created_at": "2026-08-31T05:00:00Z", "updated_at": "2026-08-31T05:01:00Z"},
]

STATUSES = {
    "/repos/octo-org/demo-app/deployments/8001/statuses": [
        {"state": "success", "environment": "production",
         "log_url": "https://gh.example.com/octo-org/demo-app/actions/runs/7001/jobs/1",
         "target_url": "", "created_at": "2026-09-01T06:02:40Z"},
        {"state": "in_progress", "environment": "production", "log_url": "",
         "target_url": "", "created_at": "2026-09-01T06:00:10Z"},
    ],
    "/repos/octo-org/demo-app/deployments/8000/statuses": [
        {"state": "failure", "environment": "staging", "log_url": "",
         "target_url": "https://gh.example.com/logs/8000",
         "created_at": "2026-08-31T05:01:00Z"},
        {"state": "queued", "environment": "staging", "log_url": "",
         "target_url": "", "created_at": "2026-08-31T05:00:05Z"},
    ],
}

ENVIRONMENTS = {"total_count": 2, "environments": [
    {"id": 1, "name": "staging", "html_url": "https://gh.example.com/env/staging"},
    {"id": 2, "name": "production", "html_url": "https://gh.example.com/env/prod"},
]}


def _make_deploy_client(deployments=None, statuses=None):
    responses = dict(statuses or STATUSES)
    responses["/repos/octo-org/demo-app/deployments"] = (
        DEPLOYMENTS if deployments is None else deployments)
    return FakeClient(
        responses=responses,
        paginated={"/repos/octo-org/demo-app/environments": ENVIRONMENTS["environments"]},
    )


class ResolveReposTests(unittest.TestCase):
    def test_explicit_repos_plus_org_plus_user_deduped(self):
        client = FakeClient(
            responses={"/repos/octo-org/demo-app": REPO},
            paginated={
                "/orgs/octo-org/repos": [REPO, dict(REPO, id=9002,
                                                    full_name="octo-org/other")],
                "/users/alice/repos": [dict(REPO, id=9003, full_name="alice/fork")],
            },
        )
        repos = resolve_repos(client, {
            "repos": ["octo-org/demo-app"],
            "organization": "octo-org",
            "user": "alice",
        })
        by_id = {rid: name for name, rid, _ in repos}
        # explicit 9001 appears once despite org listing containing it too
        self.assertEqual(sorted(by_id), ["9001", "9002", "9003"])
        self.assertEqual(by_id["9001"], "octo-org/demo-app")

    def test_unreadable_repo_skipped_not_fatal(self):
        client = FakeClient(
            responses={"/repos/octo-org/gone": RuntimeError("HTTP 404"),
                       "/repos/octo-org/demo-app": REPO},
        )
        repos = resolve_repos(client, {"repos": ["octo-org/gone", "octo-org/demo-app"]})
        self.assertEqual([rid for _, rid, _ in repos], ["9001"])

    def test_empty_scope_resolves_empty(self):
        self.assertEqual(resolve_repos(FakeClient(), {}), [])


class PaginationTests(unittest.TestCase):
    def test_page_loop_until_short_page(self):
        client = GitHubClient.__new__(GitHubClient)
        pages = {
            1: list(range(100)),
            2: list(range(30)),
        }
        calls = []

        def fake_get(path, params=None):
            calls.append(params["page"])
            return pages[params["page"]]

        client.get = fake_get
        out = client.get_paginated("/x")
        self.assertEqual(len(out), 130)
        self.assertEqual(calls, [1, 2])

    def test_wrapper_key_unwrapped(self):
        client = GitHubClient.__new__(GitHubClient)
        client.get = lambda path, params=None: {"workflows": [{"id": 1}]}
        self.assertEqual(client.get_paginated("/x", wrapper="workflows"),
                         [{"id": 1}])


class GitHubAdapterTests(unittest.TestCase):
    REPOSITORY_FIELDS = {
        "repository_id", "name", "full_path", "description", "owner_id",
        "data_source", "platform_repo_id", "url", "default_branch",
        "visibility", "language", "language_breakdown", "created_at", "updated_at",
    }

    def _adapter(self, extra_responses=None, paginated=None):
        responses = {"/repos/octo-org/demo-app/languages": {"Python": 80, "HTML": 20}}
        responses.update(extra_responses or {})
        return _make_git_adapter(FakeClient(responses=responses, paginated=paginated))

    def test_provider_name_and_factory(self):
        self.assertEqual(self._adapter().get_provider_name(), "github")
        self.assertIsInstance(create_git_adapter("github", {"repos": []}),
                              GitHubAdapter)

    def test_git_factory_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            create_git_adapter("bitbucket", {})

    def test_ci_factory_creates_actions_adapter(self):
        self.assertIsInstance(create_ci_adapter("github_actions", {"repos": []}),
                              GitHubActionsAdapter)

    def test_list_repositories_contract(self):
        repos = self._adapter().list_repositories()
        self.assertEqual(len(repos), 1)
        repo = repos[0]
        self.assertEqual(set(repo.keys()), self.REPOSITORY_FIELDS)
        self.assertEqual(repo["repository_id"], "9001")
        self.assertEqual(repo["name"], "octo-org/demo-app")
        self.assertEqual(repo["data_source"], "github")
        self.assertEqual(repo["owner_id"], "github:777")
        self.assertEqual(repo["language"], "Python")
        self.assertEqual(repo["language_breakdown"], {"Python": 80, "HTML": 20})
        self.assertEqual(repo["updated_at"], "2026-09-01T00:00:00Z")

    def test_list_repositories_skip_details(self):
        adapter = self._adapter()
        repos = adapter.list_repositories(fetch_details=False)
        self.assertEqual(repos[0]["language_breakdown"], {})
        self.assertEqual(repos[0]["language"], "Python")  # repo payload fallback

    def test_validate_config_false_without_scope(self):
        adapter = self._adapter()
        adapter._repos = []
        self.assertFalse(adapter.validate_config())

    def test_list_members_role_mapping(self):
        adapter = self._adapter(paginated={
            "/repos/octo-org/demo-app/collaborators": MEMBERS})
        members = adapter.list_repository_members("9001")
        self.assertEqual(len(members), 3)
        by_login = {m["display_name"]: m for m in members}
        self.assertEqual((by_login["alice"]["role"], by_login["alice"]["access_level"]),
                         ("owner", 50))
        self.assertEqual((by_login["bob"]["role"], by_login["bob"]["access_level"]),
                         ("developer", 30))
        self.assertEqual((by_login["carol"]["role"], by_login["carol"]["access_level"]),
                         ("guest", 10))
        self.assertEqual(by_login["alice"]["user_id"], "github:101")
        self.assertTrue(all(m["data_source"] == "github" for m in members))

    def test_list_releases_resolves_tag_commit(self):
        adapter = self._adapter(
            extra_responses={
                "/repos/octo-org/demo-app/git/refs/tags/v1.2.0":
                    {"object": {"type": "tag", "sha": "tagobjsha"}},
                "/repos/octo-org/demo-app/git/tags/tagobjsha":
                    {"object": {"type": "commit",
                                "sha": "commitsha0001112223334445556667778889990aaa"}},
            },
            paginated={"/repos/octo-org/demo-app/releases": RELEASES},
        )
        releases = adapter.list_repository_releases("9001")
        self.assertEqual(len(releases), 1)
        rel = releases[0]
        self.assertEqual(rel["release_id"], "github:9001/v1.2.0")
        self.assertEqual(rel["tag_name"], "v1.2.0")
        self.assertEqual(rel["version"], "1.2.0")
        self.assertEqual(rel["status"], "completed")
        self.assertEqual(rel["commit_sha"],
                         "commitsha0001112223334445556667778889990aaa")
        self.assertEqual(rel["release_time"], "2026-08-01T00:00:00Z")
        self.assertEqual(rel["data_source"], "github")

    def test_lightweight_tag_needs_no_second_hop(self):
        adapter = self._adapter(
            extra_responses={
                "/repos/octo-org/demo-app/git/refs/tags/v1.2.0":
                    {"object": {"type": "commit", "sha": "lightweightsha"}},
            },
            paginated={"/repos/octo-org/demo-app/releases": RELEASES},
        )
        rel = adapter.list_repository_releases("9001")[0]
        self.assertEqual(rel["commit_sha"], "lightweightsha")

    def test_tag_resolution_cached_per_process(self):
        client = FakeClient(
            responses={
                "/repos/octo-org/demo-app/git/refs/tags/v1.2.0":
                    {"object": {"type": "commit", "sha": "cachedsha"}},
            },
            paginated={"/repos/octo-org/demo-app/releases": RELEASES},
        )
        adapter = _make_git_adapter(client)
        adapter.list_repository_releases("9001")
        adapter.list_repository_releases("9001")  # second cycle: cache hit
        ref_calls = [c for c, _ in client.get_calls if "refs/tags" in c]
        self.assertEqual(len(ref_calls), 1)  # one resolution, not two

    def test_get_release_by_tag_404_returns_none(self):
        adapter = self._adapter(
            extra_responses={
                "/repos/octo-org/demo-app/releases/tags/nope":
                    RuntimeError("HTTP 404"),
            })
        self.assertIsNone(adapter.get_release_by_tag("9001", "nope"))

    def test_list_pull_requests_contract(self):
        adapter = self._adapter(paginated={
            "/repos/octo-org/demo-app/pulls": PULLS})
        prs = adapter.list_pull_requests("9001")
        self.assertEqual(len(prs), 1)
        pr = prs[0]
        self.assertEqual(pr["pr_id"], "github:9001!42")
        self.assertEqual(pr["status"], "merged")          # merged_at wins over closed
        self.assertEqual(pr["author_id"], "github:101")
        self.assertEqual(pr["reviewers"], ["github:102"])
        self.assertEqual(pr["source_branch"], "feat-x")
        self.assertEqual(pr["target_branch"], "main")
        self.assertEqual(pr["merge_commit_sha"], "mergesha222")
        self.assertEqual(pr["data_source"], "github")

    def test_pr_state_open_and_closed_unmerged(self):
        adapter = self._adapter(paginated={"/repos/octo-org/demo-app/pulls": [
            dict(PULLS[0], number=1, merged_at=None, state="open"),
            dict(PULLS[0], number=2, merged_at=None, state="closed"),
        ]})
        prs = adapter.list_pull_requests("9001")
        self.assertEqual([p["status"] for p in prs], ["open", "closed"])

    def test_git_embedded_ci_stays_empty(self):
        # GitHub Actions is a standalone ICIAdapter; the git adapter must not
        # double-produce pipeline records (same contract as codeup).
        adapter = self._adapter()
        self.assertEqual(adapter.list_pipelines("9001"), [])
        self.assertEqual(adapter.list_pipeline_runs("9001"), [])

    def test_repo_id_outside_scope_raises(self):
        adapter = self._adapter()
        with self.assertRaises(KeyError):
            adapter.list_pull_requests("9999")


class GitHubActionsAdapterTests(unittest.TestCase):
    PIPELINE_FIELDS = {
        "pipeline_id", "repository_id", "name", "file_path", "description",
        "data_source", "platform_pipeline_id", "url", "is_active",
        "created_at", "updated_at",
    }
    RUN_FIELDS = {
        "run_id", "pipeline_id", "repository_id", "number", "pr_id",
        "commit_sha", "branch", "trigger_type", "status", "conclusion",
        "data_source", "platform_run_id", "url", "triggered_by", "stages",
        "created_at", "started_at", "completed_at", "duration_seconds",
        "queue_duration_seconds",
    }

    def _adapter(self, max_runs=20):
        client = FakeClient(
            responses={"/repos/octo-org/demo-app/actions/workflows/501/runs": RUNS},
            paginated={
                "/repos/octo-org/demo-app/actions/workflows": WORKFLOWS["workflows"],
            },
        )
        return _make_actions_adapter(client, max_runs=max_runs), client

    def test_provider_name(self):
        adapter, _ = self._adapter()
        self.assertEqual(adapter.get_provider_name(), "github_actions")

    def test_validate_config_false_without_scope(self):
        adapter, _ = self._adapter()
        adapter._repos = []
        self.assertFalse(adapter.validate_config())

    def test_list_pipelines_contract(self):
        adapter, _ = self._adapter()
        pipelines = adapter.list_pipelines()
        self.assertEqual(len(pipelines), 1)
        pipe = pipelines[0]
        self.assertEqual(set(pipe.keys()), self.PIPELINE_FIELDS)
        self.assertEqual(pipe["pipeline_id"], "github_actions:9001:501")
        self.assertEqual(pipe["platform_pipeline_id"], "9001:501")
        self.assertEqual(pipe["repository_id"], "9001")
        self.assertEqual(pipe["name"], "verify")
        self.assertEqual(pipe["file_path"], ".github/workflows/verify.yml")
        self.assertTrue(pipe["is_active"])
        self.assertEqual(pipe["data_source"], "github_actions")

    def test_list_pipeline_runs_contract(self):
        adapter, _ = self._adapter()
        runs = adapter.list_pipeline_runs()
        self.assertEqual(len(runs), 2)
        for run in runs:
            self.assertEqual(set(run.keys()), self.RUN_FIELDS)
            self.assertEqual(run["data_source"], "github_actions")
            self.assertEqual(run["pipeline_id"], "github_actions:9001:501")
            self.assertEqual(run["repository_id"], "9001")

    def test_run_field_mapping(self):
        adapter, _ = self._adapter()
        runs = {r["platform_run_id"]: r for r in adapter.list_pipeline_runs()}
        ok = runs["7001"]
        self.assertEqual(ok["run_id"], "github_actions:9001:7001")
        self.assertEqual((ok["status"], ok["conclusion"]), ("success", "success"))
        self.assertEqual(ok["trigger_type"], "push")
        self.assertEqual(ok["commit_sha"],
                         "aaaabbbbccccdddd00001111222233334444")
        self.assertEqual(ok["branch"], "main")
        self.assertEqual(ok["triggered_by"], "github:101")
        self.assertEqual(ok["pr_id"], "")
        self.assertEqual(ok["duration_seconds"], 120)     # 06:00:30 → 06:02:30
        self.assertEqual(ok["queue_duration_seconds"], 30)
        self.assertEqual(ok["number"], 9)

        fail = runs["7000"]
        self.assertEqual((fail["status"], fail["conclusion"]),
                         ("failure", "failure"))
        self.assertEqual(fail["trigger_type"], "pull_request")
        self.assertEqual(fail["pr_id"], "github:9001!42")  # backfilled from run

    def test_status_conclusion_matrix(self):
        adapter, _ = self._adapter()
        base = dict(RUNS["workflow_runs"][0])
        cases = [
            ("queued", None, ("queued", "")),
            ("in_progress", None, ("in_progress", "")),
            ("waiting", None, ("queued", "")),
            ("completed", "success", ("success", "success")),
            ("completed", "neutral", ("success", "")),
            ("completed", "failure", ("failure", "failure")),
            ("completed", "timed_out", ("failure", "timeout")),
            ("completed", "cancelled", ("cancelled", "cancelled")),
            ("completed", "skipped", ("skipped", "")),
            ("surprise", None, ("queued", "")),
        ]
        for status, conclusion, want in cases:
            with self.subTest(status=status, conclusion=conclusion):
                run = dict(base, status=status, conclusion=conclusion)
                rec = adapter._map_run("9001", "github_actions:9001:501", run)
                self.assertEqual((rec["status"], rec["conclusion"]), want)
                # completed runs keep updated_at as completed_at; others ""
                if status == "completed":
                    self.assertTrue(rec["completed_at"])
                else:
                    self.assertEqual(rec["completed_at"], "")
                    self.assertEqual(rec["duration_seconds"], 0)

    def test_event_matrix(self):
        adapter, _ = self._adapter()
        base = dict(RUNS["workflow_runs"][0])
        cases = {"push": "push", "pull_request": "pull_request",
                 "pull_request_target": "pull_request", "schedule": "schedule",
                 "workflow_dispatch": "manual", "release": "manual",
                 "repository_dispatch": "manual", "": "manual"}
        for event, want in cases.items():
            with self.subTest(event=event):
                rec = adapter._map_run("9001", "github_actions:9001:501",
                                       dict(base, event=event))
                self.assertEqual(rec["trigger_type"], want)

    def test_max_runs_cap_uses_bounded_first_page(self):
        adapter, client = self._adapter(max_runs=5)
        adapter.list_pipeline_runs()
        path, params = client.get_calls[-1]
        self.assertIn("runs", path)
        self.assertEqual(params["per_page"], 5)

    def test_uncapped_lists_all_pages(self):
        adapter, client = self._adapter(max_runs=0)
        adapter.list_pipeline_runs()
        self.assertEqual(len(client.get_calls), 0)  # paginated path instead

    def test_per_repo_failure_isolated(self):
        good = FakeClient(
            responses={"/repos/octo-org/demo-app/actions/workflows/501/runs": RUNS},
            paginated={
                "/repos/octo-org/demo-app/actions/workflows": WORKFLOWS["workflows"],
                "/repos/octo-org/broken/actions/workflows":
                    RuntimeError("HTTP 500 boom"),
            },
        )
        adapter = _make_actions_adapter(good)
        adapter._repos = [
            ("octo-org/broken", "9002", dict(REPO, id=9002,
                                             full_name="octo-org/broken")),
            ("octo-org/demo-app", "9001", REPO),
        ]
        runs = adapter.list_pipeline_runs()
        self.assertEqual(len(runs), 2)
        self.assertTrue(all(r["repository_id"] == "9001" for r in runs))


class GitHubDeployAdapterTests(unittest.TestCase):
    DEPLOYMENT_FIELDS = {
        "deployment_id", "title", "description", "repository_id", "run_id",
        "environment_id", "commit_sha", "version", "status", "conclusion",
        "data_source", "platform_deployment_id", "url", "deployed_by",
        "release_id", "artifacts", "created_at", "started_at",
        "completed_at", "rollback_started_at", "rollback_completed_at",
        "duration_seconds",
    }

    def test_provider_name_and_factory(self):
        self.assertEqual(_make_deploy_adapter(_make_deploy_client())
                         .get_provider_name(), "github_cd")
        self.assertIsInstance(create_deploy_adapter("github", {"repos": []}),
                              GitHubDeployAdapter)

    def test_validate_config_false_without_scope(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        adapter._repos = []
        self.assertFalse(adapter.validate_config())

    def test_list_deployments_contract(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 2)
        for rec in deployments:
            self.assertEqual(set(rec.keys()), self.DEPLOYMENT_FIELDS)
            self.assertEqual(rec["data_source"], "github_cd")
            self.assertEqual(rec["repository_id"], "9001")
            self.assertTrue(rec["deployment_id"].startswith("github_cd:9001:"))

    def test_success_deployment_mapping_with_run_link(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        rec = [d for d in adapter.list_deployments()
               if d["deployment_id"] == "github_cd:9001:8001"][0]
        self.assertEqual((rec["status"], rec["conclusion"]), ("success", "success"))
        self.assertEqual(rec["environment_id"], "production")
        self.assertEqual(rec["commit_sha"],
                         "aaaabbbbccccdddd00001111222233334444")
        self.assertEqual(rec["version"], "aaaabbbb")
        # run_id parsed back out of the status log_url (Actions job link)
        self.assertEqual(rec["run_id"], "github_actions:9001:7001")
        self.assertEqual(rec["url"],
                         "https://gh.example.com/octo-org/demo-app/actions/runs/7001/jobs/1")
        self.assertEqual(rec["deployed_by"], "github:101")
        self.assertEqual(rec["created_at"], "2026-09-01T06:00:00Z")
        self.assertEqual(rec["started_at"], "2026-09-01T06:00:10Z")
        self.assertEqual(rec["completed_at"], "2026-09-01T06:02:40Z")
        self.assertEqual(rec["duration_seconds"], 150)
        # null description in payload → synthesized fallback
        self.assertIn("8001", rec["description"])

    def test_failure_deployment_url_falls_back_to_target_url(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        rec = [d for d in adapter.list_deployments()
               if d["deployment_id"] == "github_cd:9001:8000"][0]
        self.assertEqual((rec["status"], rec["conclusion"]), ("failure", "failure"))
        self.assertEqual(rec["url"], "https://gh.example.com/logs/8000")
        self.assertEqual(rec["run_id"], "")   # no actions link in statuses
        self.assertEqual(rec["description"], "deploy to staging")

    def test_state_matrix(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        base_dep = dict(DEPLOYMENTS[0])
        cases = [
            ("success", ("success", "success")),
            ("failure", ("failure", "failure")),
            ("error", ("failure", "failure")),
            ("inactive", ("success", "")),       # superseded, but deployed
            ("in_progress", ("in_progress", "")),
            ("queued", ("queued", "")),
            ("pending", ("queued", "")),
            ("surprise", ("queued", "")),
        ]
        for state, want in cases:
            with self.subTest(state=state):
                rec = adapter._map_deployment(
                    "octo-org/demo-app", "9001", base_dep,
                    [{"state": state, "created_at": "2026-09-01T06:02:40Z"}])
                self.assertEqual((rec["status"], rec["conclusion"]), want)

    def test_empty_statuses_degrade_gracefully(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        rec = adapter._map_deployment("octo-org/demo-app", "9001", DEPLOYMENTS[0], [])
        self.assertEqual((rec["status"], rec["conclusion"]), ("queued", ""))
        self.assertEqual(rec["completed_at"], "")
        self.assertEqual(rec["url"], "")
        self.assertEqual(rec["run_id"], "")

    def test_max_deployments_cap_uses_bounded_page(self):
        client = _make_deploy_client()
        adapter = _make_deploy_adapter(client, max_per=1)
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 1)
        path, params = client.get_calls[0]
        self.assertTrue(path.endswith("/deployments"))
        self.assertEqual(params["per_page"], 1)

    def test_per_repo_failure_isolated(self):
        client = _make_deploy_client()
        client.responses["/repos/octo-org/broken/deployments"] = \
            RuntimeError("HTTP 500 boom")
        adapter = _make_deploy_adapter(client)
        adapter._repos = [
            ("octo-org/broken", "9002", dict(REPO, id=9002,
                                             full_name="octo-org/broken")),
            ("octo-org/demo-app", "9001", REPO),
        ]
        deployments = adapter.list_deployments()
        self.assertEqual(len(deployments), 2)
        self.assertTrue(all(d["repository_id"] == "9001" for d in deployments))

    def test_list_applications_maps_environments(self):
        adapter = _make_deploy_adapter(_make_deploy_client())
        apps = adapter.list_applications()
        self.assertEqual(len(apps), 2)
        prod = [a for a in apps if a["name"].endswith("/production")][0]
        self.assertEqual(prod["name"], "octo-org/demo-app/production")
        self.assertEqual(prod["repo_url"], "https://gh.example.com/octo-org/demo-app")
        self.assertEqual(prod["dest_server"], "https://gh.example.com/env/prod")


if __name__ == "__main__":
    unittest.main()
