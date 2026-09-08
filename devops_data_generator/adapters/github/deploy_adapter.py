"""GitHub CD adapter — maps GitHub Deployments/Environments into the unified
deployment schema (see adapters/deploy_base.py for the contract).

Reads via the GitHub REST API (same ``github:`` config section as the git
provider / Actions CI axes — one token fills all three):
  - GET /repos/{o}/{r}/deployments                    → deployment records
  - GET /repos/{o}/{r}/deployments/{id}/statuses      → state + log_url
  - GET /repos/{o}/{r}/environments                   → list_applications()

Config: same ``github:`` section, plus:
  max_deployments_per_project: 20   # recent N deployments per repo per cycle
                                    # (plus one statuses call each); 0 = unlimited

Linkage: a deployment carries no workflow-run field, but the latest status
log_url/target_url typically points at the deploying Actions job
(.../actions/runs/{run_id}/jobs/...), so run_id is parsed back out of it
when present — the GitHub equivalent of GitLab's deployable.pipeline link.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..deploy_base import IDeployAdapter
from .client import GitHubClient, resolve_repos

logger = logging.getLogger(__name__)

PROVIDER_NAME = "github_cd"
DEFAULT_MAX_DEPLOYMENTS_PER_PROJECT = 20

# Latest deployment-status state → (status, conclusion). "inactive" means a
# newer deployment superseded this one: it did deploy, so success/"".
_STATE_MAP = {
    "success": ("success", "success"),
    "failure": ("failure", "failure"),
    "error": ("failure", "failure"),
    "inactive": ("success", ""),
    "in_progress": ("in_progress", ""),
    "queued": ("queued", ""),
    "pending": ("queued", ""),
}

_RUN_URL_RE = re.compile(r"/actions/runs/(\d+)")


class GitHubDeployAdapter(IDeployAdapter):
    """IDeployAdapter backed by the GitHub Deployments/Environments API."""

    def __init__(self, config: Dict[str, Any]):
        self.client = GitHubClient(config.get("api_url") or "",
                                   config.get("token") or "")
        self._config = config
        self._repos: Optional[List[Any]] = None  # lazy: resolved on first use
        max_per = config.get("max_deployments_per_project")
        self.max_deployments_per_project = (DEFAULT_MAX_DEPLOYMENTS_PER_PROJECT
                                            if max_per is None else self._safe_int(max_per))

    def _repo_scope(self) -> List[Any]:
        """(full_name, repo_id, repo_object) tuples, resolved once."""
        if self._repos is None:
            self._repos = resolve_repos(self.client, self._config)
        return self._repos

    # ---- IDeployAdapter -------------------------------------------------

    def get_provider_name(self) -> str:
        return PROVIDER_NAME

    def validate_config(self) -> bool:
        if not self._repo_scope():
            logger.error("github_cd: no repositories resolved "
                         "(repos/organization/user are all empty or unreadable)")
            return False
        return True

    def list_applications(self) -> List[Dict[str, Any]]:
        """GitHub environments ≈ deploy targets (discovery/inspection)."""
        apps: List[Dict[str, Any]] = []
        for full_name, _, obj in self._repo_scope():
            try:
                envs = self.client.get_paginated(
                    f"/repos/{full_name}/environments", wrapper="environments")
            except Exception as exc:  # noqa: BLE001 — keep other repos going
                logger.warning("github_cd: failed to list environments for %s: %s",
                               full_name, exc)
                continue
            for env in envs:
                apps.append({
                    "name": f"{full_name}/{env.get('name', '')}",
                    "repo_url": obj.get("html_url", "") or "",
                    "target_revision": "",
                    "dest_namespace": "",
                    "dest_server": env.get("html_url", "") or "",
                    "sync_status": "",
                    "health_status": "",
                })
        return apps

    def list_deployments(self) -> List[Dict[str, Any]]:
        deployments: List[Dict[str, Any]] = []
        for full_name, repo_id, _ in self._repo_scope():
            try:
                deployments.extend(self._list_repo_deployments(full_name, repo_id))
            except Exception as exc:  # noqa: BLE001 — one repo must not sink
                logger.warning("github_cd: failed to list deployments for %s: %s",
                               full_name, exc)  # the whole cycle
        logger.info("github_cd: produced %s deployment records", len(deployments))
        return deployments

    # ---- mapping ---------------------------------------------------------

    def _list_repo_deployments(self, full_name: str, repo_id: str) -> List[Dict[str, Any]]:
        if self.max_deployments_per_project > 0:
            raw = self.client.get(
                f"/repos/{full_name}/deployments",
                {"per_page": min(self.max_deployments_per_project, 100)},
            )[: self.max_deployments_per_project]
        else:
            raw = self.client.get_paginated(f"/repos/{full_name}/deployments")
        out = []
        for d in raw:
            statuses = self.client.get(
                f"/repos/{full_name}/deployments/{d.get('id')}/statuses",
                {"per_page": 100}) or []
            out.append(self._map_deployment(full_name, repo_id, d, statuses))
        return out

    def _map_deployment(self, full_name: str, repo_id: str,
                        d: Dict[str, Any], statuses: List[Dict[str, Any]]) -> Dict[str, Any]:
        dep_id = d.get("id", "")
        env_name = d.get("environment", "") or ""
        ref = d.get("ref", "") or ""
        sha = d.get("sha", "") or ""
        creator = d.get("creator") or {}
        creator_id = str(creator.get("id", "") or "") if isinstance(creator, dict) else ""

        # Statuses are returned newest first.
        latest = statuses[0] if statuses else {}
        state = latest.get("state", "") or ""
        status, conclusion = _STATE_MAP.get(state, ("queued", ""))
        earliest = statuses[-1] if statuses else {}

        log_url = latest.get("log_url", "") or latest.get("target_url", "") or ""
        run_id = ""
        m = _RUN_URL_RE.search(log_url)
        if m:
            run_id = f"github_actions:{repo_id}:{m.group(1)}"

        created_at = d.get("created_at", "") or ""
        started_at = earliest.get("created_at", "") or created_at
        terminal = state in ("success", "failure", "error", "inactive")
        completed_at = (latest.get("created_at", "") or "") if terminal else ""
        description = d.get("description") or (
            f"GitHub deployment {dep_id} of {ref}@{sha[:8]} to "
            f"{env_name or 'unknown'} (task={d.get('task', '') or 'deploy'}, state={state or 'none'})"
        )
        return {
            "deployment_id": f"{PROVIDER_NAME}:{repo_id}:{dep_id}",
            "title": f"{full_name} → {env_name or 'unknown'} ({ref}@{sha[:8]})",
            "description": description,
            "repository_id": repo_id,
            "run_id": run_id,
            "environment_id": env_name,
            "commit_sha": sha,
            "version": sha[:8],
            "status": status,
            "conclusion": conclusion,
            "data_source": PROVIDER_NAME,
            "platform_deployment_id": str(dep_id),
            "url": log_url,
            "deployed_by": f"github:{creator_id}" if creator_id else "",
            "release_id": "",
            "artifacts": "",
            "created_at": created_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "rollback_started_at": "",
            "rollback_completed_at": "",
            "duration_seconds": self._duration_seconds(started_at, completed_at),
        }

    # ---- helpers ----------------------------------------------------------

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
