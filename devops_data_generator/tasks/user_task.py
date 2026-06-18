"""Fetch user facts via IGitAdapter.list_repository_members.

Iterates over the repositories collected by ``RepositoryTask`` and collapses
per-repo member lists into a unique user roster, tracking the repos each user
appears in.

Writes the payload under ``devops.user_raw_data`` for downstream relationship
tasks.
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class UserTask(BaseTask):
    """User task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter

    def get_dependencies(self) -> List[str]:
        return ["repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("repository_raw_data", [])
        if not repositories:
            logger.warning("No repository data found in shared context")
            return []

        user_cache: Dict[str, Dict[str, Any]] = {}
        for repo in repositories:
            repository_id = str(repo.get("repository_id", "") or "")
            repository_name = repo.get("name", "Unknown")
            if not repository_id:
                logger.warning("Repository %s has no repository_id, skipping", repository_name)
                continue
            try:
                members = self.git_adapter.list_repository_members(repository_id)
            except Exception as exc:  # noqa: BLE001 — survive bad single repo
                logger.warning("Failed to fetch members for repo %s: %s", repository_name, exc)
                continue

            for member in members:
                user_id = str(member.get("user_id", "") or "")
                if not user_id:
                    continue
                repo_ref = {
                    "repository_id": repository_id,
                    "repository_name": repository_name,
                    "access_level": member.get("access_level", 0),
                    "role": member.get("role", "member"),
                }
                existing = user_cache.get(user_id)
                if existing:
                    existing.setdefault("repositories", []).append(repo_ref)
                    continue

                user_cache[user_id] = {
                    "user_id": user_id,
                    "full_name": member.get("full_name", "") or "",
                    "email": member.get("email", "") or "",
                    "display_name": member.get("display_name", "") or "",
                    "avatar_url": member.get("avatar_url", "") or "",
                    "data_source": member.get("data_source") or self.git_adapter.get_provider_name(),
                    "platform_user_id": member.get("platform_user_id", "") or "",
                    "department": member.get("department", "") or "",
                    "is_active": member.get("is_active", True),
                    "repositories": [repo_ref],
                }

        users = list(user_cache.values())
        for user in users:
            user["repository_count"] = len(user.get("repositories", []))
            # roles 从该 user 的所有 repository 成员资格聚合去重排序；
            # 此前写死 [] 从不填充是 bug，本次修复。
            user["roles"] = sorted(
                {r["role"] for r in user.get("repositories", []) if r.get("role")}
            )

        self.set_shared_data("user_list", users, "user")
        self.set_shared_data("devops.user_raw_data", users, "user")
        logger.info(
            "Fetched %s users via %s adapter",
            len(users),
            self.git_adapter.get_provider_name(),
        )
        return users

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
