"""repository_contains_pull_request relationship task.

repository → pull_request (contains), from pull_request.repository_id.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class RepositoryContainsPullRequestTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["pull_request", "repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        pull_requests = self.get_shared_data("pull_request_raw_data", [])
        if not pull_requests:
            logger.warning("No pull_request data found in shared context")
            return []

        relationships: List[Dict[str, Any]] = []
        for pr in pull_requests:
            repository_id = pr.get("repository_id", "")
            pr_id = pr.get("pr_id", "")
            if not repository_id or not pr_id:
                continue
            relationships.append(
                {
                    "__link_type__": "contains",
                    "__src_entity_id__": repository_id,
                    "__dest_entity_id__": pr_id,
                    "repository_id": repository_id,
                    "pr_id": pr_id,
                }
            )

        self.set_shared_data("repository_contains_pull_request_list", relationships, "relationship_data")
        logger.info("Generated %s repository_contains_pull_request relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
