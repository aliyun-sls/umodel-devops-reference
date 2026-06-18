"""release_contains_artifact relationship task.

release → artifact (contains). Matches release.tag_name to artifact.tag_name
(tag matching). Depends on release + docker_image (which co-produces artifacts).
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ReleaseContainsArtifactTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["release", "docker_image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        releases = self.get_shared_data("release_list", [])
        artifacts = self.get_shared_data("artifact_raw_data", [])
        if not releases or not artifacts:
            logger.warning("release_contains_artifact: missing release or artifact data")
            return []

        # Index artifacts by tag_name for exact match.
        by_tag: Dict[str, List[Dict[str, Any]]] = {}
        for art in artifacts:
            tag = art.get("tag_name", "")
            if tag:
                by_tag.setdefault(tag, []).append(art)

        relationships: List[Dict[str, Any]] = []
        for release in releases:
            tag_name = release.get("tag_name", "")
            release_id = release.get("release_id", "")
            if not tag_name or not release_id:
                continue
            for art in by_tag.get(tag_name, []):
                artifact_id = art.get("artifact_id", "")
                if not artifact_id:
                    continue
                relationships.append(
                    {
                        "__link_type__": "contains",
                        "__src_entity_id__": release_id,
                        "__dest_entity_id__": artifact_id,
                        "release_id": release_id,
                        "artifact_id": artifact_id,
                        "tag_name": tag_name,
                    }
                )

        self.set_shared_data("release_contains_artifact_list", relationships, "relationship_data")
        logger.info("Generated %s release_contains_artifact relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
