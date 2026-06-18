"""Fetch pull request facts via IGitAdapter.list_pull_requests.

Provider-agnostic: iterates over the repositories collected by ``RepositoryTask``
and calls the adapter's ``list_pull_requests`` (GitLab MR / Codeup MR).
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PullRequestTask(BaseTask):
    """Pull request task — provider-agnostic, delegates to git_adapter."""

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

        pull_requests: List[Dict[str, Any]] = []
        provider_name = self.git_adapter.get_provider_name()
        for repo in repositories:
            repository_id = str(repo.get("repository_id", "") or "")
            if not repository_id:
                continue
            try:
                prs = self.git_adapter.list_pull_requests(repository_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch pull requests for repo %s: %s", repo.get("name", ""), exc)
                continue
            for pr in prs:
                pr["data_source"] = pr.get("data_source") or provider_name
                pull_requests.append(pr)

        self.set_shared_data("pull_request_list", pull_requests, "pull_request")
        self.set_shared_data("pull_request_raw_data", pull_requests, "pull_request")
        logger.info("Fetched %s pull requests via %s adapter", len(pull_requests), provider_name)
        return pull_requests

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
