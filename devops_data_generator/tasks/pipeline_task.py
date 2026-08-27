"""Pipeline Task — fetch CI pipeline definitions via IGitAdapter.list_pipelines.

Produces ``devops.pipeline`` entity records. Pipeline definitions exist only
for providers with built-in CI (GitLab CI, ...); providers without CI return
[] via the adapter default.
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PipelineTask(BaseTask):
    """Pipeline task — provider-agnostic, delegates to git_adapter."""

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

        pipelines: List[Dict[str, Any]] = []
        for repo in repositories:
            repository_id = str(repo.get("repository_id", "") or "")
            if not repository_id:
                continue
            try:
                pipelines.extend(self.git_adapter.list_pipelines(repository_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch pipelines for repo %s: %s",
                               repo.get("name", repository_id), exc)

        self.set_shared_data("pipeline_list", pipelines, "pipeline")
        logger.info(
            "Fetched %s pipelines via %s adapter",
            len(pipelines),
            self.git_adapter.get_provider_name(),
        )
        return pipelines

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
