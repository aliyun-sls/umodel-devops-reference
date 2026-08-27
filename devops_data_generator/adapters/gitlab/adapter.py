"""GitLab implementation of IGitAdapter."""

import logging
from typing import Any, Dict, List, Optional

from ..base import IGitAdapter
from .client import GITLAB_SDK_AVAILABLE, create_gitlab_client

logger = logging.getLogger(__name__)

# GitLab access_level → human-readable role. Keep as adapter-internal because
# it is purely a GitLab convention.
ACCESS_LEVEL_ROLE = {
    50: "owner",
    40: "maintainer",
    30: "developer",
    20: "reporter",
    10: "guest",
}


class GitLabAdapter(IGitAdapter):
    """GitLab provider adapter (python-gitlab SDK)."""

    PROVIDER_NAME = "gitlab"
    DEFAULT_BRANCH_FALLBACK = "main"

    def __init__(self, config: Dict[str, Any]):
        self.gitlab_url = config.get("url", "")
        self.access_token = config.get("access_token", "")
        self.group_id = config.get("group_id")
        self.project_id = config.get("project_id")
        self.client = create_gitlab_client(self.gitlab_url, self.access_token)

    # ------------------------------------------------------------------
    # IGitAdapter implementation
    # ------------------------------------------------------------------
    def get_provider_name(self) -> str:
        return self.PROVIDER_NAME

    def get_default_branch_fallback(self) -> str:
        return self.DEFAULT_BRANCH_FALLBACK

    def validate_config(self) -> bool:
        if not GITLAB_SDK_AVAILABLE:
            logger.warning("python-gitlab is not installed")
            return False
        if not self.gitlab_url or not self.access_token:
            logger.error("Missing gitlab url or access token")
            return False
        return True

    def list_repositories(self, fetch_details: bool = True) -> List[Dict[str, Any]]:
        repositories: List[Dict[str, Any]] = []
        for project in self._iter_projects():
            detail = self.client.projects.get(project.id) if fetch_details else project
            languages = self._safe_languages(detail) if fetch_details else {}
            repo_id = str(detail.id)
            repositories.append(
                {
                    "repository_id": repo_id,
                    "name": getattr(detail, "path_with_namespace", "") or getattr(detail, "name", ""),
                    "full_path": getattr(detail, "path_with_namespace", "") or "",
                    "description": getattr(detail, "description", "") or "",
                    "owner_id": "",
                    "data_source": self.PROVIDER_NAME,
                    "platform_repo_id": repo_id,
                    "url": getattr(detail, "web_url", "") or "",
                    "default_branch": getattr(detail, "default_branch", "") or self.DEFAULT_BRANCH_FALLBACK,
                    "visibility": getattr(detail, "visibility", "") or "",
                    "language": self._primary_language(languages),
                    "language_breakdown": languages,
                    "created_at": self._safe_dt(getattr(detail, "created_at", "")),
                    "updated_at": self._safe_dt(getattr(detail, "last_activity_at", "")),
                }
            )
        return repositories

    def list_repository_members(self, repo_id: str) -> List[Dict[str, Any]]:
        project = self.client.projects.get(int(repo_id))
        members = []
        for member in project.members_all.list(all=True):
            user_id = str(getattr(member, "id", ""))
            members.append(
                {
                    "user_id": f"{self.PROVIDER_NAME}:{user_id}" if user_id else "",
                    "full_name": getattr(member, "name", "") or getattr(member, "username", ""),
                    "email": getattr(member, "email", "") or "",
                    "display_name": getattr(member, "username", "") or "",
                    "avatar_url": getattr(member, "avatar_url", "") or "",
                    "data_source": self.PROVIDER_NAME,
                    "platform_user_id": user_id,
                    "department": "",
                    "is_active": getattr(member, "state", "active") == "active",
                    "role": ACCESS_LEVEL_ROLE.get(getattr(member, "access_level", 0) or 0, "member"),
                    "access_level": getattr(member, "access_level", 0) or 0,
                }
            )
        return members

    def list_repository_releases(self, repo_id: str) -> List[Dict[str, Any]]:
        project = self.client.projects.get(int(repo_id))
        return [self._normalize_release(repo_id, release) for release in project.releases.list(all=True)]

    def get_release_by_tag(self, repo_id: str, tag: str) -> Optional[Dict[str, Any]]:
        try:
            project = self.client.projects.get(int(repo_id))
            release = project.releases.get(tag)
            return self._normalize_release(repo_id, release)
        except Exception as exc:  # noqa: BLE001 — GitLab SDK raises various types
            logger.warning("Release tag %s not found for repo %s: %s", tag, repo_id, exc)
            return None

    def list_pull_requests(self, repo_id: str) -> List[Dict[str, Any]]:
        """Return merge requests for a repository in the unified pull_request schema."""
        project = self.client.projects.get(int(repo_id))
        pull_requests: List[Dict[str, Any]] = []
        for mr in project.mergerequests.list(all=True, state="all"):
            pr_num = getattr(mr, "iid", "")
            pr_id = f"{self.PROVIDER_NAME}:{repo_id}!{pr_num}" if pr_num else ""
            author = getattr(mr, "author", {}) or {}
            author_id = str(author.get("id", "") or "") if isinstance(author, dict) else ""
            reviewers = []
            for reviewer in getattr(mr, "reviewers", None) or []:
                reviewer_id = str(reviewer.get("id", "") or "") if isinstance(reviewer, dict) else ""
                if reviewer_id:
                    reviewers.append(f"{self.PROVIDER_NAME}:{reviewer_id}")
            pull_requests.append(
                {
                    "pr_id": pr_id,
                    "project_id": "",
                    "repository_id": repo_id,
                    "number": pr_num,
                    "title": getattr(mr, "title", "") or "",
                    "description": getattr(mr, "description", "") or "",
                    "author_id": f"{self.PROVIDER_NAME}:{author_id}" if author_id else "",
                    "reviewers": reviewers,
                    "source_branch": getattr(mr, "source_branch", "") or "",
                    "target_branch": getattr(mr, "target_branch", "") or "",
                    "source_commit_sha": getattr(mr, "sha", "") or "",
                    "merge_commit_sha": getattr(mr, "merge_commit_sha", "") or "",
                    "status": self._map_mr_state(getattr(mr, "state", "")),
                    "data_source": self.PROVIDER_NAME,
                    "platform_pr_id": str(pr_num),
                    "url": getattr(mr, "web_url", "") or "",
                    "created_at": self._safe_dt(getattr(mr, "created_at", "")),
                    "updated_at": self._safe_dt(getattr(mr, "updated_at", "")),
                    "merged_at": self._safe_dt(getattr(mr, "merged_at", "")),
                    "closed_at": self._safe_dt(getattr(mr, "closed_at", "")),
                }
            )
        return pull_requests

    # ------------------------------------------------------------------
    # CI pipeline (IGitAdapter optional capability)
    # ------------------------------------------------------------------
    def list_pipelines(self, repo_id: str) -> List[Dict[str, Any]]:
        """Pipeline definitions = the project's CI config file.

        GitLab has no pipeline-definition API object; a project with CI
        enabled has exactly one definition at its ci_config_path (default
        .gitlab-ci.yml). Projects with CI disabled yield no record.
        """
        project = self.client.projects.get(int(repo_id))
        ci_path = getattr(project, "ci_config_path", "") or ".gitlab-ci.yml"
        if not getattr(project, "jobs_enabled", True):
            return []
        # jobs_enabled is the GitLab default even for repos with NO CI config;
        # the definition only exists if the config file is actually there.
        # (Otherwise every repo would claim a phantom pipeline entity.)
        default_branch = getattr(project, "default_branch", "") or self.DEFAULT_BRANCH_FALLBACK
        try:
            project.files.head(file_path=ci_path, ref=default_branch)
        except Exception as exc:  # noqa: BLE001 — 404 means no CI config
            logger.info("repo %s: no CI config at %s (%s); no pipeline entity",
                        repo_id, ci_path, exc)
            return []
        platform_id = f"{repo_id}:{ci_path}"
        web_url = getattr(project, "web_url", "") or ""
        return [{
            "pipeline_id": f"{self.PROVIDER_NAME}:{platform_id}",
            "repository_id": repo_id,
            "name": f"{getattr(project, 'path_with_namespace', '') or repo_id} CI",
            "file_path": ci_path,
            "description": "",
            "data_source": self.PROVIDER_NAME,
            "platform_pipeline_id": platform_id,
            "url": f"{web_url}/-/pipelines" if web_url else "",
            "is_active": True,
            "created_at": self._safe_dt(getattr(project, "created_at", "")),
            "updated_at": self._safe_dt(getattr(project, "last_activity_at", "")),
        }]

    def list_pipeline_runs(self, repo_id: str) -> List[Dict[str, Any]]:
        """Pipeline executions (project.pipelines.list)."""
        project = self.client.projects.get(int(repo_id))
        ci_path = getattr(project, "ci_config_path", "") or ".gitlab-ci.yml"
        pipeline_id = f"{self.PROVIDER_NAME}:{repo_id}:{ci_path}"
        runs: List[Dict[str, Any]] = []
        for p in project.pipelines.list(all=True):
            status = self._map_pipeline_status(getattr(p, "status", ""))
            user = getattr(p, "user", None) or {}
            username = user.get("username", "") if isinstance(user, dict) else ""
            runs.append({
                "run_id": f"{self.PROVIDER_NAME}:{repo_id}:{getattr(p, 'id', '')}",
                "pipeline_id": pipeline_id,
                "repository_id": repo_id,
                "number": getattr(p, "iid", 0) or 0,
                "pr_id": "",
                "commit_sha": getattr(p, "sha", "") or "",
                "branch": getattr(p, "ref", "") or "",
                "trigger_type": self._map_pipeline_source(getattr(p, "source", "")),
                "status": status,
                "conclusion": self._map_pipeline_conclusion(status),
                "data_source": self.PROVIDER_NAME,
                "platform_run_id": str(getattr(p, "id", "") or ""),
                "url": getattr(p, "web_url", "") or "",
                "triggered_by": f"{self.PROVIDER_NAME}:{username}" if username else "",
                "stages": "",
                "created_at": self._safe_dt(getattr(p, "created_at", "")),
                "started_at": self._safe_dt(getattr(p, "started_at", "")),
                "completed_at": self._safe_dt(getattr(p, "finished_at", "")),
                "duration_seconds": int(getattr(p, "duration", 0) or 0),
                "queue_duration_seconds": int(getattr(p, "queued_duration", 0) or 0),
            })
        return runs

    @staticmethod
    def _map_pipeline_status(status: str) -> str:
        """GitLab pipeline status → contract enum."""
        return {
            "created": "queued", "waiting_for_resource": "queued",
            "preparing": "queued", "pending": "queued", "scheduled": "queued",
            "manual": "queued",
            "running": "in_progress",
            "success": "success",
            "failed": "failure",
            "canceled": "cancelled",
            "skipped": "skipped",
        }.get(status, "queued")

    @staticmethod
    def _map_pipeline_conclusion(status: str) -> str:
        return {"success": "success", "failure": "failure",
                "cancelled": "cancelled"}.get(status, "")

    @staticmethod
    def _map_pipeline_source(source: str) -> str:
        """GitLab pipeline source → contract trigger_type enum."""
        return {
            "push": "push",
            "merge_request_event": "pull_request",
            "schedule": "schedule",
            "web": "manual", "api": "manual", "trigger": "manual",
        }.get(source, "manual")

    # ------------------------------------------------------------------
    # GitLab-specific helpers
    # ------------------------------------------------------------------
    def _iter_projects(self) -> List[Any]:
        if self.project_id:
            return [self.client.projects.get(self.project_id)]
        if self.group_id:
            group = self.client.groups.get(self.group_id)
            # include_subgroups=True covers descendant-group projects (previously
            # only direct group projects). The per-project projects.get() is NOT
            # redundant: group.projects.list() returns partial GroupProject objects
            # that lack .languages(), so full Project objects are still required.
            listed = group.projects.list(all=True, include_subgroups=True)
            return [self.client.projects.get(p.id) for p in listed]
        return self.client.projects.list(membership=True, all=True)

    def _safe_languages(self, project: Any) -> Dict[str, float]:
        try:
            return project.languages() or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch languages for %s: %s", getattr(project, "id", "?"), exc)
            return {}

    @staticmethod
    def _primary_language(language_stats: Dict[str, float]) -> str:
        if not language_stats:
            return ""
        return max(language_stats.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _safe_dt(value: Any) -> str:
        if not value:
            return ""
        try:
            return str(value).replace("T", "T")
        except Exception:  # noqa: BLE001
            return str(value)

    @staticmethod
    def _map_mr_state(state: str) -> str:
        return {
            "opened": "open",
            "merged": "merged",
            "closed": "closed",
        }.get(state, "open")

    def _normalize_release(self, repo_id: str, release: Any) -> Dict[str, Any]:
        author = getattr(release, "author", {}) or {}
        commit = getattr(release, "commit", {}) or {}
        commit_sha = commit.get("id", "") if isinstance(commit, dict) else ""
        tag = release.tag_name
        return {
            "release_id": f"{self.PROVIDER_NAME}:{repo_id}/{tag}",
            "repository_id": repo_id,
            "name": getattr(release, "name", "") or tag,
            "version": tag.lstrip("v") if tag else "",
            "description": getattr(release, "description", "") or "",
            "release_type": "",  # derived by release_classifier in the task
            "status": "completed",
            "data_source": self.PROVIDER_NAME,
            "platform_release_id": f"{repo_id}/{tag}",
            "url": getattr(release, "_links", {}).get("self", "") if isinstance(getattr(release, "_links", None), dict) else "",
            "created_by": author.get("name", "") if isinstance(author, dict) else "",
            "tag_name": tag,
            "target_commitish": commit.get("id", "") if isinstance(commit, dict) else "",
            "commit_sha": commit_sha,
            "release_time": getattr(release, "released_at", "") or getattr(release, "created_at", "") or "",
            "tag_type": "release",
        }
