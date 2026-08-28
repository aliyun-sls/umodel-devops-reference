"""Pipeline Run Task — fetch CI pipeline executions from git-embedded CI and
standalone CI adapters (Jenkins, ...).
"""

import logging
from typing import Any, Dict, List, Optional

from adapters import IGitAdapter, ICIAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PipelineRunTask(BaseTask):
    """Pipeline run task — merges git-embedded CI and standalone CI adapters."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter,
                 ci_adapters: Optional[List[ICIAdapter]] = None):
        super().__init__(config)
        self.git_adapter = git_adapter
        self.ci_adapters = ci_adapters or []

    def get_dependencies(self) -> List[str]:
        return ["repository", "pipeline"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("repository_raw_data", [])
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

        for ci in self.ci_adapters:
            try:
                runs.extend(ci.list_pipeline_runs())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch pipeline runs from %s: %s",
                               ci.get_provider_name(), exc)

        self.set_shared_data("pipeline_run_list", runs, "pipeline_run")
        logger.info(
            "Fetched %s pipeline runs (git=%s + %s CI adapters)",
            len(runs),
            self.git_adapter.get_provider_name(),
            len(self.ci_adapters),
        )
        return runs

    def validate_config(self) -> bool:
        ok = self.git_adapter.validate_config()
        for ci in self.ci_adapters:
            ok = ci.validate_config() and ok
        return ok
