"""GitHub implementation of IGitAdapter (stdlib urllib, no SDK).

Reads via the GitHub REST API (github.com or GHES):
  - repos from explicit ``repos:`` list / ``organization:`` / ``user:`` scope
  - GET /repos/{o}/{r}/collaborators           → members
  - GET /repos/{o}/{r}/releases                → releases
  - GET /repos/{o}/{r}/git/refs/tags/{tag}     → release commit resolution
  - GET /repos/{o}/{r}/pulls?state=all         → pull requests
  - GET /repos/{o}/{r}/languages               → language breakdown

Config (app_config.yaml section ``github``):
  token: ""                       # PAT / fine-grained token; empty = anonymous
                                  # (60 req/h/IP — fine for smoke tests only)
  api_url: "https://api.github.com"   # override for GHES
  repos: ["owner/name"]           # explicit allowlist (primary scope knob)
  organization: ""                # optional: discover all repos of an org
  user: ""                        # optional: discover repos of a user
  fetch_details: true             # per-repo languages + tag→commit resolution

Anonymous access works for public repos (list collaborators of public repos
is allowed); a token is still recommended for sane rate limits.
"""

import logging
from typing import Any, Dict, List, Optional

from ..base import IGitAdapter
from .client import DEFAULT_API_URL, GitHubClient, resolve_repos

logger = logging.getLogger(__name__)

# GitHub role_name → (unified role, numeric access_level). Mirrors the
# GitLab ACCESS_LEVEL_ROLE ladder (50 owner → 10 guest).
ROLE_MAP = {
    "admin": ("owner", 50),
    "maintain": ("maintainer", 40),
    "write": ("developer", 30),
    "triage": ("reporter", 20),
    "read": ("guest", 10),
}


class GitHubAdapter(IGitAdapter):
    """GitHub provider adapter (REST API, stdlib urllib)."""

    PROVIDER_NAME = "github"
    DEFAULT_BRANCH_FALLBACK = "main"

    def __init__(self, config: Dict[str, Any]):
        self.token = config.get("token") or ""
        self.api_url = (config.get("api_url") or DEFAULT_API_URL).rstrip("/")
        self.fetch_details = bool(config.get("fetch_details", True))
        self.client = GitHubClient(self.api_url, self.token)
        self._config = config
        self._repos: Optional[List[Any]] = None  # lazy: resolved on first use
        # tag → commit sha is effectively immutable; caching avoids re-resolving
        # hundreds of releases every cycle (229 releases ≈ 300 calls/cycle on a
        # release-heavy repo, which would eat the 5000 req/h token budget).
        self._tag_sha_cache: Dict[str, str] = {}

    def _repo_scope(self) -> List[Any]:
        """(full_name, repo_id, repo_object) tuples, resolved once."""
        if self._repos is None:
            self._repos = resolve_repos(self.client, self._config)
        return self._repos

    # ------------------------------------------------------------------
    # IGitAdapter implementation
    # ------------------------------------------------------------------
    def get_provider_name(self) -> str:
        return self.PROVIDER_NAME

    def get_default_branch_fallback(self) -> str:
        return self.DEFAULT_BRANCH_FALLBACK

    def validate_config(self) -> bool:
        if not self._repo_scope():
            logger.error("github: no repositories resolved "
                         "(repos/organization/user are all empty or unreadable)")
            return False
        if not self.token:
            logger.warning("github.token is empty — anonymous access is "
                           "limited to 60 requests/hour/IP")
        return True

    def list_repositories(self, fetch_details: bool = True) -> List[Dict[str, Any]]:
        fetch_details = fetch_details and self.fetch_details
        repositories: List[Dict[str, Any]] = []
        for full_name, repo_id, obj in self._repo_scope():
            languages: Dict[str, float] = {}
            if fetch_details:
                languages = self._safe_languages(full_name)
            owner = obj.get("owner") or {}
            owner_id = owner.get("id", "") if isinstance(owner, dict) else ""
            repositories.append({
                "repository_id": repo_id,
                "name": full_name,
                "full_path": full_name,
                "description": obj.get("description") or "",
                "owner_id": f"{self.PROVIDER_NAME}:{owner_id}" if owner_id else "",
                "data_source": self.PROVIDER_NAME,
                "platform_repo_id": repo_id,
                "url": obj.get("html_url", "") or "",
                "default_branch": obj.get("default_branch", "") or self.DEFAULT_BRANCH_FALLBACK,
                "visibility": obj.get("visibility", "") or "",
                "language": obj.get("language") or self._primary_language(languages),
                "language_breakdown": languages,
                "created_at": obj.get("created_at", "") or "",
                "updated_at": obj.get("pushed_at", "") or obj.get("updated_at", "") or "",
            })
        return repositories

    def list_repository_members(self, repo_id: str) -> List[Dict[str, Any]]:
        full_name = self._full_name(repo_id)
        members: List[Dict[str, Any]] = []
        for c in self.client.get_paginated(f"/repos/{full_name}/collaborators"):
            user_id = str(c.get("id", "") or "")
            role, level = ROLE_MAP.get(c.get("role_name", ""), ("member", 0))
            members.append({
                "user_id": f"{self.PROVIDER_NAME}:{user_id}" if user_id else "",
                "full_name": c.get("name") or c.get("login", "") or "",
                "email": c.get("email") or "",
                "display_name": c.get("login", "") or "",
                "avatar_url": c.get("avatar_url", "") or "",
                "data_source": self.PROVIDER_NAME,
                "platform_user_id": user_id,
                "department": "",
                "is_active": True,
                "role": role,
                "access_level": level,
            })
        return members

    def list_repository_releases(self, repo_id: str) -> List[Dict[str, Any]]:
        full_name = self._full_name(repo_id)
        return [
            self._normalize_release(repo_id, full_name, r)
            for r in self.client.get_paginated(f"/repos/{full_name}/releases")
        ]

    def get_release_by_tag(self, repo_id: str, tag: str) -> Optional[Dict[str, Any]]:
        full_name = self._full_name(repo_id)
        try:
            release = self.client.get(f"/repos/{full_name}/releases/tags/{tag}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Release tag %s not found for repo %s: %s", tag, repo_id, exc)
            return None
        return self._normalize_release(repo_id, full_name, release)

    def list_pull_requests(self, repo_id: str) -> List[Dict[str, Any]]:
        full_name = self._full_name(repo_id)
        pull_requests: List[Dict[str, Any]] = []
        for pr in self.client.get_paginated(f"/repos/{full_name}/pulls",
                                            {"state": "all"}):
            number = pr.get("number", "")
            author = pr.get("user") or {}
            author_id = str(author.get("id", "") or "") if isinstance(author, dict) else ""
            reviewers = []
            for reviewer in pr.get("requested_reviewers") or []:
                reviewer_id = str(reviewer.get("id", "") or "") if isinstance(reviewer, dict) else ""
                if reviewer_id:
                    reviewers.append(f"{self.PROVIDER_NAME}:{reviewer_id}")
            head = pr.get("head") or {}
            base = pr.get("base") or {}
            pull_requests.append({
                "pr_id": f"{self.PROVIDER_NAME}:{repo_id}!{number}" if number != "" else "",
                "project_id": "",
                "repository_id": repo_id,
                "number": number,
                "title": pr.get("title", "") or "",
                "description": pr.get("body", "") or "",
                "author_id": f"{self.PROVIDER_NAME}:{author_id}" if author_id else "",
                "reviewers": reviewers,
                "source_branch": head.get("ref", "") or "",
                "target_branch": base.get("ref", "") or "",
                "source_commit_sha": head.get("sha", "") or "",
                "merge_commit_sha": pr.get("merge_commit_sha", "") or "",
                "status": self._map_pr_state(pr),
                "data_source": self.PROVIDER_NAME,
                "platform_pr_id": str(number),
                "url": pr.get("html_url", "") or "",
                "created_at": pr.get("created_at", "") or "",
                "updated_at": pr.get("updated_at", "") or "",
                "merged_at": pr.get("merged_at", "") or "",
                "closed_at": pr.get("closed_at", "") or "",
            })
        return pull_requests

    # ------------------------------------------------------------------
    # GitHub-specific helpers
    # ------------------------------------------------------------------
    def _full_name(self, repo_id: str) -> str:
        """Numeric repo_id → owner/name for path construction."""
        for full_name, rid, _ in self._repo_scope():
            if rid == str(repo_id):
                return full_name
        raise KeyError(f"github: repo_id {repo_id} is outside the configured scope")

    def _safe_languages(self, full_name: str) -> Dict[str, float]:
        try:
            return self.client.get(f"/repos/{full_name}/languages") or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch languages for %s: %s", full_name, exc)
            return {}

    def _resolve_tag_commit(self, full_name: str, tag: str) -> str:
        """tag → commit sha (annotated tags need one dereference hop).

        Results are cached per process: a tag points at the same commit for
        its whole lifetime in practice (force-pushed tags are the rare
        exception and self-heal on process restart).
        """
        if not tag or not self.fetch_details:
            return ""
        if tag in self._tag_sha_cache:
            return self._tag_sha_cache[tag]
        sha = self._resolve_tag_commit_uncached(full_name, tag)
        self._tag_sha_cache[tag] = sha
        return sha

    def _resolve_tag_commit_uncached(self, full_name: str, tag: str) -> str:
        try:
            ref = self.client.get(f"/repos/{full_name}/git/refs/tags/{tag}")
            obj = ref.get("object") or {}
            if obj.get("type") == "commit":
                return obj.get("sha", "") or ""
            if obj.get("type") == "tag":
                tag_obj = self.client.get(
                    f"/repos/{full_name}/git/tags/{obj.get('sha')}")
                inner = tag_obj.get("object") or {}
                return inner.get("sha", "") or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to resolve tag %s commit for %s: %s",
                           tag, full_name, exc)
        return ""

    def _normalize_release(self, repo_id: str, full_name: str,
                           release: Dict[str, Any]) -> Dict[str, Any]:
        tag = release.get("tag_name", "") or ""
        author = release.get("author") or {}
        author_login = author.get("login", "") if isinstance(author, dict) else ""
        return {
            "release_id": f"{self.PROVIDER_NAME}:{repo_id}/{tag}",
            "repository_id": repo_id,
            "name": release.get("name", "") or tag,
            "version": tag.lstrip("v") if tag else "",
            "description": release.get("body", "") or "",
            "release_type": "",  # derived by release_classifier in the task
            "status": "draft" if release.get("draft") else "completed",
            "data_source": self.PROVIDER_NAME,
            "platform_release_id": f"{repo_id}/{tag}",
            "url": release.get("html_url", "") or "",
            "created_by": author_login,
            "tag_name": tag,
            "target_commitish": release.get("target_commitish", "") or "",
            # GitHub releases carry only a ref name; resolving to a commit
            # sha costs one refs call per release (fetch_details gate).
            "commit_sha": self._resolve_tag_commit(full_name, tag),
            "release_time": release.get("published_at", "") or release.get("created_at", "") or "",
            "tag_type": "release",
        }

    @staticmethod
    def _map_pr_state(pr: Dict[str, Any]) -> str:
        if pr.get("merged_at"):
            return "merged"
        return "closed" if pr.get("state") == "closed" else "open"

    @staticmethod
    def _primary_language(language_stats: Dict[str, float]) -> str:
        if not language_stats:
            return ""
        return max(language_stats.items(), key=lambda item: item[1])[0]
