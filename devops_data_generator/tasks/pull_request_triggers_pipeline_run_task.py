"""pull_request_triggers_pipeline_run relationship task.

pull_request → pipeline_run (triggers). Matching rule:
  1. primary: run.pr_id == pr.pr_id (when the CI system reports it);
  2. fallback: run.commit_sha matches the PR's merge_commit_sha or
     source_commit_sha (GitLab MR pipelines don't always expose the MR id
     on the pipeline list payload).

Matching is scoped to the same repository to avoid cross-repo sha collisions.
Depends on pull_request + pipeline_run.
"""

import logging
from typing import Any, Dict, List

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PullRequestTriggersPipelineRunTask(BaseTask):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = "relationship"

    def get_dependencies(self) -> List[str]:
        return ["pull_request", "pipeline_run"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        prs = self.get_shared_data("pull_request_raw_data", []) \
            or self.get_shared_data("pull_request_list", [])
        runs = self.get_shared_data("pipeline_run_list", [])
        if not prs or not runs:
            logger.warning("pull_request_triggers_pipeline_run: missing pr or run data")
            return []

        # Index PRs by id and by commit sha, scoped per repository.
        by_id: Dict[str, Dict[str, Any]] = {}
        by_sha: Dict[str, Dict[str, Any]] = {}
        for pr in prs:
            repo = str(pr.get("repository_id", "") or "")
            pr_id = pr.get("pr_id", "")
            if pr_id:
                by_id[f"{repo}|{pr_id}"] = pr
            for sha in (pr.get("merge_commit_sha", ""), pr.get("source_commit_sha", "")):
                if sha:
                    by_sha[f"{repo}|{sha}"] = pr

        relationships: List[Dict[str, Any]] = []
        seen = set()
        for run in runs:
            run_id = run.get("run_id", "")
            repo = str(run.get("repository_id", "") or "")
            if not run_id or not repo:
                continue
            pr = None
            if run.get("pr_id"):
                pr = by_id.get(f"{repo}|{run['pr_id']}")
            if pr is None and run.get("commit_sha"):
                pr = by_sha.get(f"{repo}|{run['commit_sha']}")
            if not pr or not pr.get("pr_id"):
                continue
            key = (pr["pr_id"], run_id)
            if key in seen:
                continue
            seen.add(key)
            relationships.append({
                "__link_type__": "triggers",
                "__src_entity_id__": pr["pr_id"],
                "__dest_entity_id__": run_id,
                "pr_id": pr["pr_id"],
                "run_id": run_id,
                "commit_sha": run.get("commit_sha", ""),
            })

        self.set_shared_data("pull_request_triggers_pipeline_run_list", relationships, "relationship_data")
        logger.info("Generated %s pull_request_triggers_pipeline_run relationships", len(relationships))
        return relationships

    def validate_config(self) -> bool:
        return True
