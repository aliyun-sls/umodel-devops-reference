"""Fetch developer facts via IGitAdapter.list_repository_members.

Iterates over the repositories collected by ``CodeRepositoryTask`` and
collapses per-repo member lists into a unique developer roster, tracking
the repos each developer appears in.

Writes the same payload under two shared-context keys for backwards
compatibility:
    - ``developer_list`` (consumed by developer_manages_code_repository_task)
    - ``devops.developer_raw_data`` (consumed by other relationship tasks)
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class DeveloperTask(BaseTask):
    """Developer task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter

    def get_dependencies(self) -> List[str]:
        return ["code_repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("code_repository_raw_data", [])
        if not repositories:
            logger.warning("No repository data found in shared context")
            return []

        developer_cache: Dict[str, Dict[str, Any]] = {}
        for repo in repositories:
            repo_id = str(repo.get("repo_id", "") or "")
            repo_name = repo.get("repo_name", "Unknown")
            if not repo_id:
                logger.warning("Repository %s has no repo_id, skipping", repo_name)
                continue
            try:
                members = self.git_adapter.list_repository_members(repo_id)
            except Exception as exc:  # noqa: BLE001 — survive bad single repo
                logger.warning("Failed to fetch members for repo %s: %s", repo_name, exc)
                continue

            for member in members:
                user_id = str(member.get("user_id", "") or "")
                if not user_id:
                    continue
                repo_ref = {
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "access_level": member.get("access_level", 0),
                    "role": member.get("role", "member"),
                }
                existing = developer_cache.get(user_id)
                if existing:
                    existing.setdefault("repositories", []).append(repo_ref)
                    continue

                developer_cache[user_id] = {
                    "dev_id": user_id,
                    "user_id": user_id,
                    "name": member.get("name", "") or member.get("username", ""),
                    "email": member.get("email", "") or "",
                    "username": member.get("username", "") or "",
                    "avatar_url": member.get("avatar_url", "") or "",
                    "role": member.get("role", "member"),
                    "state": member.get("state", "active") or "active",
                    "repositories": [repo_ref],
                }

        developers = list(developer_cache.values())
        for dev in developers:
            dev["repo_count"] = len(dev.get("repositories", []))

        # Double-write — keep both keys to support downstream tasks that
        # read either name. See plan §6 for the historical context.
        self.set_shared_data("developer_list", developers, "developer")
        self.set_shared_data("devops.developer_raw_data", developers, "developer")
        logger.info(
            "Fetched %s developers via %s adapter",
            len(developers),
            self.git_adapter.get_provider_name(),
        )
        return developers

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
