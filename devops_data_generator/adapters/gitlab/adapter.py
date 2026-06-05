"""GitLab implementation of IGitAdapter."""

import logging
from typing import Any, Dict, List, Optional

from ..base import IGitAdapter
from .client import GITLAB_SDK_AVAILABLE, create_gitlab_client

logger = logging.getLogger(__name__)

# GitLab access_level → human-readable role (from demo CodeRepositoryTask /
# DeveloperTask). Keep as adapter-internal because it is purely a GitLab
# convention.
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
            repositories.append(
                {
                    "repo_id": str(detail.id),
                    "repo_name": getattr(detail, "path_with_namespace", "") or getattr(detail, "name", ""),
                    "repo_url": getattr(detail, "web_url", "") or "",
                    "language": self._primary_language(languages),
                    "language_breakdown": languages,
                    "framework": "",
                    "description": getattr(detail, "description", "") or "",
                    "default_branch": getattr(detail, "default_branch", "") or self.DEFAULT_BRANCH_FALLBACK,
                    "path_with_namespace": getattr(detail, "path_with_namespace", "") or "",
                    "visibility": getattr(detail, "visibility", "") or "",
                }
            )
        return repositories

    def list_repository_members(self, repo_id: str) -> List[Dict[str, Any]]:
        project = self.client.projects.get(int(repo_id))
        members = []
        for member in project.members_all.list(all=True):
            access_level = getattr(member, "access_level", 0) or 0
            members.append(
                {
                    "user_id": str(getattr(member, "id", "")),
                    "name": getattr(member, "name", "") or getattr(member, "username", ""),
                    "email": getattr(member, "email", "") or "",
                    "username": getattr(member, "username", "") or "",
                    "avatar_url": getattr(member, "avatar_url", "") or "",
                    "role": ACCESS_LEVEL_ROLE.get(access_level, f"level_{access_level}"),
                    "access_level": access_level,
                    "state": getattr(member, "state", "active") or "active",
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

    # ------------------------------------------------------------------
    # GitLab-specific helpers
    # ------------------------------------------------------------------
    def _iter_projects(self) -> List[Any]:
        if self.project_id:
            return [self.client.projects.get(self.project_id)]
        if self.group_id:
            group = self.client.groups.get(self.group_id)
            return [self.client.projects.get(p.id) for p in group.projects.list(all=True)]
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

    def _normalize_release(self, repo_id: str, release: Any) -> Dict[str, Any]:
        author = getattr(release, "author", {}) or {}
        commit = getattr(release, "commit", {}) or {}
        commit_sha = commit.get("id", "") if isinstance(commit, dict) else ""
        return {
            "release_id": f"{repo_id}/{release.tag_name}",
            "repo_id": repo_id,
            "tag": release.tag_name,
            "commit_sha": commit_sha,
            "release_notes": getattr(release, "description", "") or "",
            "release_time": getattr(release, "released_at", "") or getattr(release, "created_at", "") or "",
            "author": author.get("name", "") if isinstance(author, dict) else "",
            "author_email": "",
            "tag_type": "release",
        }
