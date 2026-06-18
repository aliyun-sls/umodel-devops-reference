"""Fetch repository facts via an IGitAdapter implementation.

Provider-specific API calls live in ``devops_data_generator/adapters/{gitlab,codeup}/``.
This task shapes the unified adapter output into the SLS-bound dict and writes
it to the shared context for downstream tasks.
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class RepositoryTask(BaseTask):
    """Repository task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter
        self.fetch_details = bool(config.get("fetch_details", True))

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        provider_name = self.git_adapter.get_provider_name()
        repositories: List[Dict[str, Any]] = []
        for repo in self.git_adapter.list_repositories(fetch_details=self.fetch_details):
            repo["repository_id"] = str(repo.get("repository_id", "") or "")
            # data_source is already stamped by the adapter; ensure it survives.
            repo["data_source"] = repo.get("data_source") or provider_name
            repositories.append(repo)

        self.set_shared_data("repositories", repositories, "repository")
        self.set_shared_data("repository_raw_data", repositories, "repository")
        logger.info("Fetched %s repositories via %s adapter", len(repositories), provider_name)
        return repositories

    def get_dependencies(self) -> List[str]:
        return []

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
