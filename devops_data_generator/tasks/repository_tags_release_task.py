"""repository_tags_release relationship task.

Direction is reversed vs the legacy code_release_sourced_from_code_repository:
repository → release (repository tags release), matching design doc verb.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class RepositoryTagsReleaseTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["repository", "release"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        releases = self.get_shared_data("release_list", [])
        if not releases:
            logger.warning("No release data found in shared context")
            return []

        relationships: List[Dict[str, Any]] = []
        for release in releases:
            repository_id = release.get("repository_id", "")
            release_id = release.get("release_id", "")
            if not repository_id or not release_id:
                continue
            relationships.append(
                {
                    "__link_type__": "tags",
                    "__src_entity_id__": repository_id,
                    "__dest_entity_id__": release_id,
                    "repository_id": repository_id,
                    "release_id": release_id,
                    "tag_name": release.get("tag_name", ""),
                }
            )

        self.set_shared_data("repository_tags_release_list", relationships, "relationship_data")
        logger.info("Generated %s repository_tags_release relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
