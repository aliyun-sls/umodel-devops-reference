"""GitLab CD adapter — maps GitLab Environments/Deployments into the unified
deployment schema (see adapters/deploy_base.py for the contract).

GitLab CD is a first-class capability of the git platform (same philosophy as
GitLab CI on IGitAdapter), so this adapter rides on the same ``gitlab:``
config section — no separate credentials. The orchestrator wires it
automatically when ``git_provider.type == "gitlab"``.

Reads via python-gitlab (reuses GitLabAdapter's client + project scoping):
  - project.deployments.list(...)   → unified deployment records
  - project.environments.list(...)  → list_applications() (discovery)

Optional extra keys in the ``gitlab:`` config section:
  max_deployments_per_project: 20   # recent N deployments per project per
                                    # cycle (id desc); 0 = unlimited

Note: the deployment API always reflects *recorded* deploy jobs — projects
without ``environment:`` jobs simply return an empty list.
"""

import logging
from typing import Any, Dict, List

from ..deploy_base import IDeployAdapter
from .adapter import GitLabAdapter

logger = logging.getLogger(__name__)

# GitLab deployment status → contract enum (deploy_base.py).
_STATUS_MAP = {
    "created": "queued",
    "blocked": "queued",   # waiting on an approval/unlock gate
    "running": "in_progress",
    "success": "success",
    "failed": "failure",
    "canceled": "cancelled",
}

# Contract conclusion enum is success/failure/rolled_back (or "").
_CONCLUSION_MAP = {
    "success": "success",
    "failure": "failure",
}


class GitLabDeployAdapter(IDeployAdapter):
    """IDeployAdapter backed by the GitLab Environments/Deployments API."""

    PROVIDER_NAME = "gitlab_cd"
    DEFAULT_MAX_DEPLOYMENTS_PER_PROJECT = 20

    def __init__(self, config: Dict[str, Any]):
        # Composition over duplication: GitLabAdapter owns the client
        # (python-gitlab, soft import) and the group/project scoping rules.
        self.git = GitLabAdapter(config)
        max_per = config.get("max_deployments_per_project")
        self.max_deployments_per_project = self.DEFAULT_MAX_DEPLOYMENTS_PER_PROJECT \
            if max_per is None else self._safe_int(max_per)

    # ------------------------------------------------------------------
    # IDeployAdapter implementation
    # ------------------------------------------------------------------
    def get_provider_name(self) -> str:
        return self.PROVIDER_NAME

    def validate_config(self) -> bool:
        return self.git.validate_config()

    def list_applications(self) -> List[Dict[str, Any]]:
        """GitLab environments ≈ deploy targets (discovery/inspection)."""
        apps: List[Dict[str, Any]] = []
        for project in self._iter_projects():
            project_path = getattr(project, "path_with_namespace", "") or str(getattr(project, "id", ""))
            try:
                environments = project.environments.list(all=True)
            except Exception as exc:  # noqa: BLE001 — keep other projects going
                logger.warning("gitlab_cd: failed to list environments for project %s: %s",
                               project_path, exc)
                continue
            for env in environments:
                apps.append({
                    "name": f"{project_path}/{getattr(env, 'name', '')}",
                    "repo_url": getattr(project, "web_url", "") or "",
                    "target_revision": "",
                    "dest_namespace": "",
                    "dest_server": getattr(env, "external_url", "") or "",
                    "sync_status": "",
                    "health_status": getattr(env, "state", "") or "",
                })
        return apps

    def list_deployments(self) -> List[Dict[str, Any]]:
        deployments: List[Dict[str, Any]] = []
        for project in self._iter_projects():
            repo_id = str(getattr(project, "id", "") or "")
            if not repo_id:
                continue
            try:
                deployments.extend(self._list_project_deployments(project, repo_id))
            except Exception as exc:  # noqa: BLE001 — one bad project must not
                logger.warning("gitlab_cd: failed to list deployments for project %s: %s",
                               repo_id, exc)  # kill the whole cycle
        logger.info("gitlab_cd: produced %s deployment records", len(deployments))
        return deployments

    # ------------------------------------------------------------------
    # mapping
    # ------------------------------------------------------------------
    def _list_project_deployments(self, project: Any, repo_id: str) -> List[Dict[str, Any]]:
        if self.max_deployments_per_project > 0:
            # First page only, newest first. per_page caps at 100 server-side.
            raw = project.deployments.list(
                order_by="id", sort="desc",
                per_page=min(self.max_deployments_per_project, 100),
            )[: self.max_deployments_per_project]
        else:
            raw = project.deployments.list(all=True, order_by="id", sort="desc")
        return [self._map_deployment(project, repo_id, d) for d in raw]

    def _map_deployment(self, project: Any, repo_id: str, d: Any) -> Dict[str, Any]:
        env = getattr(d, "environment", None)
        env = env if isinstance(env, dict) else {}
        env_name = env.get("name", "") or ""
        # deployable = the CI job that performed the deploy; None when the job
        # was deleted/retried away — degrade to empty fields, never raise.
        deployable = getattr(d, "deployable", None)
        deployable = deployable if isinstance(deployable, dict) else {}

        dep_id = getattr(d, "id", "")
        iid = getattr(d, "iid", "") or dep_id
        ref = getattr(d, "ref", "") or ""
        sha = getattr(d, "sha", "") or ""
        raw_status = getattr(d, "status", "") or ""
        status = _STATUS_MAP.get(raw_status, "queued")
        conclusion = _CONCLUSION_MAP.get(status, "")

        user = getattr(d, "user", None)
        username = user.get("username", "") if isinstance(user, dict) else ""

        pipeline = deployable.get("pipeline")
        pipeline_id = pipeline.get("id") if isinstance(pipeline, dict) else None
        # run_id reuses the pipeline_run entity id format from
        # GitLabAdapter.list_pipeline_runs so deployments point back at the
        # exact pipeline_run node that produced them.
        run_id = f"{GitLabAdapter.CI_DATA_SOURCE}:{repo_id}:{pipeline_id}" if pipeline_id else ""

        project_path = getattr(project, "path_with_namespace", "") or repo_id
        return {
            "deployment_id": f"{self.PROVIDER_NAME}:{repo_id}:{dep_id}",
            "title": f"{project_path} → {env_name or 'unknown'} ({ref}@{sha[:8]})",
            "description": (
                f"GitLab deployment #{iid} of {ref}@{sha[:8]} to "
                f"{env_name or 'unknown'} via job "
                f"{deployable.get('name', '') or 'unknown'} (status={raw_status})"
            ),
            "repository_id": repo_id,
            "run_id": run_id,
            "environment_id": env_name,
            "commit_sha": sha,
            "version": sha[:8],
            "status": status,
            "conclusion": conclusion,
            "data_source": self.PROVIDER_NAME,
            "platform_deployment_id": str(dep_id),
            "url": deployable.get("web_url", "") or "",
            "deployed_by": f"gitlab:{username}" if username else "",
            "release_id": "",
            "artifacts": "",
            "created_at": str(getattr(d, "created_at", "") or ""),
            "started_at": str(deployable.get("started_at", "") or ""),
            "completed_at": str(deployable.get("finished_at", "") or ""),
            "rollback_started_at": "",
            "rollback_completed_at": "",
            "duration_seconds": self._safe_int(deployable.get("duration")),
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _iter_projects(self) -> List[Any]:
        return self.git._iter_projects()

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
