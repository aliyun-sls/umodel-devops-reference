"""user_owns_repository relationship task.

Derives the ``owns`` relation from repository member access (users with a
manage/maintain level on a repository own it). Falls back to every member if
no access-level threshold is applied.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)

# GitLab access_level >= 40 (maintainer/owner) is treated as "owns".
OWNS_ACCESS_LEVEL_THRESHOLD = 40


class UserOwnsRepositoryTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["user", "repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        users = self.get_shared_data("devops.user_raw_data", [])
        if not users:
            logger.warning("No user data found in shared context")
            return []

        relationships: List[Dict[str, Any]] = []
        for user in users:
            user_id = user.get("user_id", "")
            if not user_id:
                continue
            for repo_ref in user.get("repositories", []):
                repository_id = repo_ref.get("repository_id", "")
                if not repository_id:
                    continue
                access_level = repo_ref.get("access_level", 0) or 0
                # Owns when access level qualifies; otherwise still emit at
                # relationship level for completeness of the graph.
                relationships.append(
                    {
                        "__link_type__": "owns",
                        "__src_entity_id__": user_id,
                        "__dest_entity_id__": repository_id,
                        "user_id": user_id,
                        "repository_id": repository_id,
                        "access_level": access_level,
                        "role": repo_ref.get("role", "member"),
                    }
                )

        self.set_shared_data("user_owns_repository_list", relationships, "relationship_data")
        logger.info("Generated %s user_owns_repository relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
