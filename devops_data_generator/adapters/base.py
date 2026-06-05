"""Git provider adapter abstract base.

Three git tasks (developer / code_repository / code_release) call into
implementations of `IGitAdapter`. Each provider supplies its own subclass
mapping the provider-native API into the unified output schema documented
below.

Unified output schemas
----------------------
``list_repositories()`` items:
    {repo_id: str, repo_name: str, repo_url: str, language: str,
     framework: str, description: str, default_branch: str,
     path_with_namespace: str | None, visibility: str | None,
     language_breakdown: dict | None}

``list_repository_members(repo_id)`` items:
    {user_id: str, name: str, email: str, username: str,
     avatar_url: str, role: str, access_level: int, state: str}

``list_repository_releases(repo_id)`` items:
    {release_id: str, repo_id: str, repo_name: str, tag: str,
     commit_sha: str, release_notes: str, release_time: str,
     author: str, author_email: str, tag_type: str}
``release_type`` is NOT set by the adapter — call sites apply
``tasks.utils.release_classifier`` to keep classification consistent
across providers.

``get_provider_name()`` returns the literal value written into the
``git_provider`` field of every repository record (``"gitlab"`` or
``"aliyun"``).
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
    def get_release_by_tag(self, repo_id: str, tag: str) -> Optional[Dict[str, Any]]:
        """Return a single release identified by tag, or None if missing."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Literal value for the ``git_provider`` field (e.g. "gitlab")."""

    @abstractmethod
    def get_default_branch_fallback(self) -> str:
        """Default branch name when the upstream API returns empty."""

    @abstractmethod
    def validate_config(self) -> bool:
        """Confirm credentials / endpoint / SDK availability."""
