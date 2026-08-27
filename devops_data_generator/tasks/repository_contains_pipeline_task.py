"""repository_contains_pipeline relationship task.

repository → pipeline (contains). One edge per pipeline definition, linked by
repository_id. Depends on repository + pipeline.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class RepositoryContainsPipelineTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["repository", "pipeline"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        pipelines = self.get_shared_data("pipeline_list", [])
        if not pipelines:
            logger.warning("repository_contains_pipeline: no pipeline data")
            return []

        relationships: List[Dict[str, Any]] = []
        for p in pipelines:
            repository_id = str(p.get("repository_id", "") or "")
            pipeline_id = p.get("pipeline_id", "")
            if not repository_id or not pipeline_id:
                continue
            relationships.append({
                "__link_type__": "contains",
                "__src_entity_id__": repository_id,
                "__dest_entity_id__": pipeline_id,
                "repository_id": repository_id,
                "pipeline_id": pipeline_id,
            })

        self.set_shared_data("repository_contains_pipeline_list", relationships, "relationship_data")
        logger.info("Generated %s repository_contains_pipeline relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
