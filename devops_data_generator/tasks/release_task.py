"""Fetch release facts via IGitAdapter.list_repository_releases.

Uses ``release_classifier`` to derive ``release_type`` consistently
across providers.
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask
from .utils.release_classifier import classify_release_type

logger = logging.getLogger(__name__)


class ReleaseTask(BaseTask):
    """Release task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter
        self.release_tag = config.get("release_tag")

    def get_dependencies(self) -> List[str]:
        return ["repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("repository_raw_data", [])
        if not repositories:
            logger.warning("No repository data found in shared context")
            return []

        releases: List[Dict[str, Any]] = []
        for repo in repositories:
            repository_id = str(repo.get("repository_id", "") or "")
            repository_name = repo.get("name", "Unknown")
            if not repository_id:
                continue

            try:
                if self.release_tag:
                    one = self.git_adapter.get_release_by_tag(repository_id, self.release_tag)
                    raw_list = [one] if one else []
                else:
                    raw_list = self.git_adapter.list_repository_releases(repository_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch releases for repo %s: %s", repository_name, exc)
                continue

            for raw in raw_list:
                if not raw:
                    continue
                tag_name = raw.get("tag_name", "")
                release_type = classify_release_type(tag_name) if tag_name else raw.get("release_type", "")
                releases.append(
                    {
                        "release_id": raw.get("release_id", f"{repository_id}/{tag_name}"),
                        "repository_id": repository_id,
                        "name": raw.get("name", "") or tag_name,
                        "version": raw.get("version", tag_name.lstrip("v") if tag_name else ""),
                        "description": raw.get("description", ""),
                        "release_type": release_type,
                        "status": raw.get("status", "completed"),
                        "data_source": raw.get("data_source") or self.git_adapter.get_provider_name(),
                        "platform_release_id": raw.get("platform_release_id", ""),
                        "url": raw.get("url", ""),
                        "created_by": raw.get("created_by", "") or "Unknown",
                        "tag_name": tag_name,
                        "target_commitish": raw.get("target_commitish", ""),
                        "created_at": raw.get("release_time", ""),
                        "commit_sha": raw.get("commit_sha", ""),
                        "tag_type": raw.get("tag_type", "release"),
                    }
                )

        self.set_shared_data("release_list", releases, "release")
        logger.info(
            "Fetched %s releases via %s adapter",
            len(releases),
            self.git_adapter.get_provider_name(),
        )
        return releases

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
