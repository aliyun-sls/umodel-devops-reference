"""release_relates_to_deployment relationship task.

release → deployment (relates_to). A release is linked to a deployment when
the deployment's ``commit_sha`` matches the release's ``target_commitish``
(or, as a fallback, the release ``tag_name`` equals the deployment
``version``). Depends on release + deployment.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ReleaseRelatesToDeploymentTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["release", "deployment"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        releases = self.get_shared_data("release_list", [])
        deployments = self.get_shared_data("deployment_raw_data", [])
        if not releases or not deployments:
            logger.warning("release_relates_to_deployment: missing release or deployment data")
            return []

        # Index releases by commitish and by tag for O(1) matching.
        by_commitish: Dict[str, Dict[str, Any]] = {}
        by_tag: Dict[str, Dict[str, Any]] = {}
        for rel in releases:
            commitish = rel.get("target_commitish", "") or rel.get("commit_sha", "")
            if commitish:
                by_commitish[commitish] = rel
            tag = rel.get("tag_name", "")
            if tag:
                by_tag[tag] = rel

        relationships: List[Dict[str, Any]] = []
        for dep in deployments:
            deployment_id = dep.get("deployment_id", "")
            commit_sha = dep.get("commit_sha", "")
            version = dep.get("version", "")
            if not deployment_id:
                continue
            rel = by_commitish.get(commit_sha) or by_tag.get(version)
            if not rel:
                continue
            release_id = rel.get("release_id", "")
            if not release_id:
                continue
            relationships.append(
                {
                    "__link_type__": "relates_to",
                    "__src_entity_id__": release_id,
                    "__dest_entity_id__": deployment_id,
                    "release_id": release_id,
                    "deployment_id": deployment_id,
                    "commit_sha": commit_sha,
                }
            )

        self.set_shared_data("release_relates_to_deployment_list", relationships, "relationship_data")
        logger.info("Generated %s release_relates_to_deployment relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
