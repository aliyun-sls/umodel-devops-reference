"""Git provider adapter abstract base.

Three git tasks (repository / user / release) call into
implementations of `IGitAdapter`. Each provider supplies its own subclass
mapping the provider-native API into the unified output schema documented
below.

Unified output schemas
----------------------
``list_repositories()`` items:
    {repository_id, name, full_path, description, owner_id,
     data_source, platform_repo_id, url, default_branch, visibility,
     language, language_breakdown, created_at, updated_at}

``list_repository_members(repo_id)`` items:
    {user_id, full_name, email, display_name, avatar_url,
     data_source, platform_user_id, department, is_active,
     role, access_level}

``list_repository_releases(repo_id)`` / ``get_release_by_tag`` items:
    {release_id, repository_id, name, version, description, release_type,
     status, data_source, platform_release_id, url, created_by,
     tag_name, target_commitish, commit_sha, release_time, tag_type}
``release_type`` is NOT set by the adapter — call sites apply
``tasks.utils.release_classifier`` to keep classification consistent
across providers.

``list_pull_requests(repo_id)`` items:
    {pr_id, project_id, repository_id, number, title, description,
     author_id, source_branch, target_branch, source_commit_sha,
     merge_commit_sha, status, data_source, platform_pr_id, url,
     created_at, updated_at, merged_at, closed_at}

``get_provider_name()`` returns the literal value written into the
``data_source`` field of every record (``"gitlab"`` or ``"codeup"``).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IGitAdapter(ABC):
    """Unified interface for git providers (GitLab / codeup / ...)."""

    @abstractmethod
    def list_repositories(self, fetch_details: bool = True) -> List[Dict[str, Any]]:
        """Return repositories in the unified schema.

        ``fetch_details=False`` lets providers that require N+1 calls for
        descriptions / languages skip them (codeup ListRepositories
        returns minimal fields; GetRepository is per-repo).
        """

    @abstractmethod
    def list_repository_members(self, repo_id: str) -> List[Dict[str, Any]]:
        """Return members for a single repository."""

    @abstractmethod
    def list_repository_releases(self, repo_id: str) -> List[Dict[str, Any]]:
        """Return releases for a single repository."""

    @abstractmethod
    def get_release_by_tag(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Return a single release identified by tag, or None if missing."""

    @abstractmethod
    def list_pull_requests(self, repo_id: str) -> List[Dict[str, Any]]:
        """Return pull requests / merge requests for a single repository."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Literal value written into the ``data_source`` field (e.g. ``"gitlab"``)."""

    @abstractmethod
    def get_default_branch_fallback(self) -> str:
        """Default branch name when the upstream API returns empty."""

    @abstractmethod
    def validate_config(self) -> bool:
        """Confirm credentials / endpoint / SDK availability."""
