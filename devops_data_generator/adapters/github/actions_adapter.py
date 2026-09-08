"""GitHub Actions adapter — maps workflows/runs into the unified CI schemas
(see adapters/ci_base.py for the contract).

GitHub Actions is a standalone CI axis (ICIAdapter), NOT parasitic on the
git adapter like GitLab CI: Actions records are already repo-scoped by the
API, so one adapter serves both the ``git_provider.type=github`` case and
the cross-provider case (e.g. codeup git + GitHub Actions CI side by side).

Reads via the GitHub REST API:
  - GET /repos/{o}/{r}/actions/workflows                  → definitions
  - GET /repos/{o}/{r}/actions/workflows/{id}/runs        → executions

Config: the same ``github:`` section as GitHubAdapter (token/api_url/
repos/organization/user), plus:
  max_runs_per_workflow: 20     # recent runs per workflow per cycle; 0 = all

A workflow run carries head_sha/head_branch/actor natively, so commit_sha,
branch and triggered_by need no repo_mapping or detail calls. pr_id is
filled from the run's pull_requests[] when present.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..ci_base import ICIAdapter
from .client import GitHubClient, resolve_repos

logger = logging.getLogger(__name__)

PROVIDER_NAME = "github_actions"
DEFAULT_MAX_RUNS_PER_WORKFLOW = 20

# run.status → unified status (ci_base contract).
_STATUS_MAP = {
    "queued": "queued",
    "requested": "queued",
    "waiting": "queued",
    "pending": "queued",
    "in_progress": "in_progress",
}

# run.conclusion (when status == "completed") → (status, conclusion).
_CONCLUSION_MAP = {
    "success": ("success", "success"),
    "neutral": ("success", ""),
    "failure": ("failure", "failure"),
    "startup_failure": ("failure", "failure"),
    "timed_out": ("failure", "timeout"),
    "cancelled": ("cancelled", "cancelled"),
    "skipped": ("skipped", ""),
    "action_required": ("failure", ""),
    "stale": ("failure", ""),
}

# run.event → unified trigger_type.
_EVENT_MAP = {
    "push": "push",
    "pull_request": "pull_request",
    "pull_request_target": "pull_request",
    "schedule": "schedule",
}


class GitHubActionsAdapter(ICIAdapter):
    """ICIAdapter implementation backed by the GitHub Actions REST API."""

    def __init__(self, config: Dict[str, Any]):
        self.client = GitHubClient(config.get("api_url") or "",
                                   config.get("token") or "")
        self._config = config
        self._repos: Optional[List[Any]] = None  # lazy: resolved on first use
        max_runs = config.get("max_runs_per_workflow")
        self.max_runs_per_workflow = (DEFAULT_MAX_RUNS_PER_WORKFLOW
                                      if max_runs is None else self._safe_int(max_runs))

    def _repo_scope(self) -> List[Any]:
        """(full_name, repo_id, repo_object) tuples, resolved once."""
        if self._repos is None:
            self._repos = resolve_repos(self.client, self._config)
        return self._repos

    # ---- ICIAdapter ---------------------------------------------------

    def get_provider_name(self) -> str:
        return PROVIDER_NAME

    def validate_config(self) -> bool:
        if not self._repo_scope():
            logger.error("github_actions: no repositories resolved "
                         "(repos/organization/user are all empty or unreadable)")
            return False
        return True

    def list_pipelines(self) -> List[Dict[str, Any]]:
        pipelines: List[Dict[str, Any]] = []
        for full_name, repo_id, _ in self._repo_scope():
            try:
                workflows = self.client.get_paginated(
                    f"/repos/{full_name}/actions/workflows", wrapper="workflows")
            except Exception as exc:  # noqa: BLE001 — one repo must not sink others
                logger.warning("github_actions: failed to list workflows for %s: %s",
                               full_name, exc)
                continue
            for wf in workflows:
                wf_id = wf.get("id", "")
                if not wf_id:
                    continue
                pipelines.append({
                    "pipeline_id": f"{PROVIDER_NAME}:{repo_id}:{wf_id}",
                    "repository_id": repo_id,
                    "name": wf.get("name", "") or "",
                    "file_path": wf.get("path", "") or "",
                    "description": "",
                    "data_source": PROVIDER_NAME,
                    "platform_pipeline_id": f"{repo_id}:{wf_id}",
                    "url": wf.get("html_url", "") or "",
                    "is_active": wf.get("state", "") == "active",
                    "created_at": wf.get("created_at", "") or "",
                    "updated_at": wf.get("updated_at", "") or "",
                })
        logger.info("github_actions: produced %s pipeline records", len(pipelines))
        return pipelines

    def list_pipeline_runs(self) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for full_name, repo_id, _ in self._repo_scope():
            for pipeline_id, wf_id in self._list_workflow_ids(full_name, repo_id):
                try:
                    items = self._list_workflow_runs(full_name, wf_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("github_actions: failed to list runs for %s workflow %s: %s",
                                   full_name, wf_id, exc)
                    continue
                for run in items:
                    runs.append(self._map_run(repo_id, pipeline_id, run))
        logger.info("github_actions: produced %s pipeline_run records", len(runs))
        return runs

    # ---- mapping --------------------------------------------------------

    def _list_workflow_ids(self, full_name: str, repo_id: str) -> List[Tuple[str, Any]]:
        """(pipeline_id, workflow_id) pairs for one repo."""
        try:
            workflows = self.client.get_paginated(
                f"/repos/{full_name}/actions/workflows", wrapper="workflows")
        except Exception as exc:  # noqa: BLE001
            logger.warning("github_actions: failed to list workflows for %s: %s",
                           full_name, exc)
            return []
        return [(f"{PROVIDER_NAME}:{repo_id}:{wf.get('id')}", wf.get("id"))
                for wf in workflows if wf.get("id")]

    def _list_workflow_runs(self, full_name: str, wf_id: Any) -> List[Dict[str, Any]]:
        if self.max_runs_per_workflow > 0:
            # First page only, newest first (API default ordering).
            data = self.client.get(
                f"/repos/{full_name}/actions/workflows/{wf_id}/runs",
                {"per_page": min(self.max_runs_per_workflow, 100)})
            items = (data.get("workflow_runs") or [])[: self.max_runs_per_workflow]
        else:
            items = self.client.get_paginated(
                f"/repos/{full_name}/actions/workflows/{wf_id}/runs",
                wrapper="workflow_runs")
        return items

    def _map_run(self, repo_id: str, pipeline_id: str,
                 run: Dict[str, Any]) -> Dict[str, Any]:
        raw_status = run.get("status", "") or ""
        raw_conclusion = run.get("conclusion", "") or ""
        if raw_status == "completed":
            status, conclusion = _CONCLUSION_MAP.get(raw_conclusion, ("failure", ""))
        else:
            status, conclusion = _STATUS_MAP.get(raw_status, "queued"), ""

        actor = run.get("actor") or {}
        actor_id = str(actor.get("id", "") or "") if isinstance(actor, dict) else ""

        pull_requests = run.get("pull_requests") or []
        pr_number = ""
        if pull_requests and isinstance(pull_requests[0], dict):
            pr_number = str(pull_requests[0].get("number", "") or "")

        created_at = run.get("created_at", "") or ""
        started_at = run.get("run_started_at", "") or ""
        completed_at = (run.get("updated_at", "") or "") if raw_status == "completed" else ""
        run_id = run.get("id", "")
        return {
            "run_id": f"{PROVIDER_NAME}:{repo_id}:{run_id}",
            "pipeline_id": pipeline_id,
            "repository_id": repo_id,
            "number": run.get("run_number", 0) or 0,
            "pr_id": f"github:{repo_id}!{pr_number}" if pr_number else "",
            "commit_sha": run.get("head_sha", "") or "",
            "branch": run.get("head_branch", "") or "",
            "trigger_type": _EVENT_MAP.get(run.get("event", "") or "", "manual"),
            "status": status,
            "conclusion": conclusion,
            "data_source": PROVIDER_NAME,
            "platform_run_id": str(run_id),
            "url": run.get("html_url", "") or "",
            "triggered_by": f"github:{actor_id}" if actor_id else "",
            "stages": "",
            "created_at": created_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": self._duration_seconds(started_at, completed_at),
            "queue_duration_seconds": self._duration_seconds(created_at, started_at),
        }

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _duration_seconds(started: str, finished: str) -> int:
        """ISO8601 pair → seconds; 0 when either missing (same rule as argocd)."""
        if not started or not finished:
            return 0
        from datetime import datetime, timezone

        def _parse(s: str) -> Optional[Any]:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
            except (ValueError, TypeError):
                return None
        a, b = _parse(started), _parse(finished)
        if not a or not b:
            return 0
        return max(0, int((b - a).total_seconds()))
