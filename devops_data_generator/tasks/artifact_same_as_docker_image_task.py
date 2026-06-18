"""artifact_same_as_docker_image relationship task (decision B).

artifact → docker_image (same_as). Co-produced by DockerImageTask: every
docker_image carries an ``artifact_id`` that pairs it to its abstract artifact.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ArtifactSameAsDockerImageTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["docker_image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        images = self.get_shared_data("docker_image_raw_data", [])
        if not images:
            logger.warning("No docker_image data found in shared context")
            return []

        relationships: List[Dict[str, Any]] = []
        for image in images:
            artifact_id = image.get("artifact_id", "")
            docker_image_id = image.get("docker_image_id", "")
            if not artifact_id or not docker_image_id:
                continue
            relationships.append(
                {
                    "__link_type__": "same_as",
                    "__src_entity_id__": artifact_id,
                    "__dest_entity_id__": docker_image_id,
                    "artifact_id": artifact_id,
                    "docker_image_id": docker_image_id,
                }
            )

        self.set_shared_data("artifact_same_as_docker_image_list", relationships, "relationship_data")
        logger.info("Generated %s artifact_same_as_docker_image relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
