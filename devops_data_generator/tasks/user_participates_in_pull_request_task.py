"""user_participates_in_pull_request relationship task.

Derived from PR author and reviewers: user → pull_request (participates_in).
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class UserParticipatesInPullRequestTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["user", "pull_request"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        pull_requests = self.get_shared_data("pull_request_raw_data", [])
        if not pull_requests:
            logger.warning("No pull_request data found in shared context")
            return []

        relationships: List[Dict[str, Any]] = []
        for pr in pull_requests:
            pr_id = pr.get("pr_id", "")
            if not pr_id:
                continue
            author_id = pr.get("author_id", "")
            if author_id:
                relationships.append(
                    {
                        "__link_type__": "participates_in",
                        "__src_entity_id__": author_id,
                        "__dest_entity_id__": pr_id,
                        "user_id": author_id,
                        "pr_id": pr_id,
                        "participation": "author",
                    }
                )
            for reviewer_id in pr.get("reviewers", []) or []:
                if reviewer_id:
                    relationships.append(
                        {
                            "__link_type__": "participates_in",
                            "__src_entity_id__": reviewer_id,
                            "__dest_entity_id__": pr_id,
                            "user_id": reviewer_id,
                            "pr_id": pr_id,
                            "participation": "reviewer",
                        }
                    )

        self.set_shared_data("user_participates_in_pull_request_list", relationships, "relationship_data")
        logger.info("Generated %s user_participates_in_pull_request relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
