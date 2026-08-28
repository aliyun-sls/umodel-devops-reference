"""Pipeline Task — fetch CI pipeline definitions from git-embedded CI and
standalone CI adapters.

Sources:
  - IGitAdapter.list_pipelines(repo_id) per repository (GitLab CI, ...);
  - each ICIAdapter (Jenkins, ...) without repo scoping.
"""

import logging
from typing import Any, Dict, List, Optional

from adapters import IGitAdapter, ICIAdapter
from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PipelineTask(BaseTask):
    """Pipeline task — merges git-embedded CI and standalone CI adapters."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter,
                 ci_adapters: Optional[List[ICIAdapter]] = None):
        super().__init__(config)
        self.git_adapter = git_adapter
        self.ci_adapters = ci_adapters or []

    def get_dependencies(self) -> List[str]:
        return ["repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("repository_raw_data", [])
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

        for ci in self.ci_adapters:
            try:
                pipelines.extend(ci.list_pipelines())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch pipelines from %s: %s",
                               ci.get_provider_name(), exc)

        self.set_shared_data("pipeline_list", pipelines, "pipeline")
        logger.info(
            "Fetched %s pipelines (git=%s + %s CI adapters)",
            len(pipelines),
            self.git_adapter.get_provider_name(),
            len(self.ci_adapters),
        )
        return pipelines

    def validate_config(self) -> bool:
        ok = self.git_adapter.validate_config()
        for ci in self.ci_adapters:
            ok = ci.validate_config() and ok
        return ok
