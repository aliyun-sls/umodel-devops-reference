"""artifact task — passthrough for the abstract artifact entity (decision B).

``DockerImageTask`` co-produces artifact records and stores them under the
``artifact_raw_data`` shared-context key. This task simply drains that key so
the orchestrator can generate + send the ``artifact`` entity. The artifact
entity is never fetched from an external source on its own; it is always a
by-product of a concrete artifact producer.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ArtifactTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "entity"

    def get_dependencies(self) -> List[str]:
        return ["docker_image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        artifacts = self.get_shared_data("artifact_raw_data", [])
        if not artifacts:
            logger.info("No paired artifact data in shared context")
            return []
        logger.info("Drained %s artifact records", len(artifacts))
        return artifacts

    def validate_config(self) -> bool:
        return True

    def get_task_name(self) -> str:
        return "artifact"
