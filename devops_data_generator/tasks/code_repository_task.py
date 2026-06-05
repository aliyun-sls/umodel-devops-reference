"""Fetch repository facts via an IGitAdapter implementation.

Provider-specific API calls live in
``devops_data_generator/adapters/{gitlab,codeup}/``. This task only
shapes the unified adapter output into the SLS-bound dict and writes it
to the shared context for downstream tasks.
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class CodeRepositoryTask(BaseTask):
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
            # Adapter returns repo_id as string already; enforce here to
            # protect against future drift.
            repo["repo_id"] = str(repo.get("repo_id", "") or "")
            # Stamp git_provider so downstream tasks / SLS see the source.
            repo["git_provider"] = provider_name
            repositories.append(repo)

        self.set_shared_data("code_repos", repositories, "code_repository")
        self.set_shared_data("code_repository_raw_data", repositories, "code_repository")
        logger.info("Fetched %s repositories via %s adapter", len(repositories), provider_name)
        return repositories

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
