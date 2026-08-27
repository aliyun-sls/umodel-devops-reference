"""Pipeline Run Task — fetch CI pipeline executions via IGitAdapter.list_pipeline_runs.

Produces ``devops.pipeline_run`` entity records (build/test executions).
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PipelineRunTask(BaseTask):
    """Pipeline run task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter

    def get_dependencies(self) -> List[str]:
        return ["repository", "pipeline"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("repository_raw_data", [])
        if not repositories:
            logger.warning("No repository data found in shared context")
            return []

        runs: List[Dict[str, Any]] = []
        for repo in repositories:
            repository_id = str(repo.get("repository_id", "") or "")
            if not repository_id:
                continue
            try:
                runs.extend(self.git_adapter.list_pipeline_runs(repository_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch pipeline runs for repo %s: %s",
                               repo.get("name", repository_id), exc)

        self.set_shared_data("pipeline_run_list", runs, "pipeline_run")
        logger.info(
            "Fetched %s pipeline runs via %s adapter",
            len(runs),
            self.git_adapter.get_provider_name(),
        )
        return runs

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
