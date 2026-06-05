"""Fetch release facts via IGitAdapter.list_repository_releases.

Uses ``release_classifier`` to derive ``release_type`` consistently
across providers (GitLab's Releases API used to hard-code
``"release"``; codeup's tag heuristic had a substring-match bug — both
now share the regex-based classifier).
"""

import logging
from typing import Any, Dict, List

from adapters import IGitAdapter
from .base_task import BaseTask
from .utils.release_classifier import classify_release_type

logger = logging.getLogger(__name__)


class CodeReleaseTask(BaseTask):
    """Release task — provider-agnostic, delegates to git_adapter."""

    def __init__(self, config: Dict[str, Any], git_adapter: IGitAdapter):
        super().__init__(config)
        self.git_adapter = git_adapter
        # Optional: when set, fetch only this single tag per repo
        # (originally a GitLab-only knob; codeup adapter degrades to list+filter).
        self.release_tag = config.get("release_tag")

    def get_dependencies(self) -> List[str]:
        return ["code_repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        repositories = self.get_shared_data("code_repository_raw_data", [])
        if not repositories:
            logger.warning("No repository data found in shared context")
            return []

        releases: List[Dict[str, Any]] = []
        for repo in repositories:
            repo_id = str(repo.get("repo_id", "") or "")
            repo_name = repo.get("repo_name", "Unknown")
            if not repo_id:
                continue

            try:
                if self.release_tag:
                    one = self.git_adapter.get_release_by_tag(repo_id, self.release_tag)
                    raw_list = [one] if one else []
                else:
                    raw_list = self.git_adapter.list_repository_releases(repo_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch releases for repo %s: %s", repo_name, exc)
                continue

            for raw in raw_list:
                if not raw:
                    continue
                tag = raw.get("tag", "")
                releases.append(
                    {
                        "release_id": raw.get("release_id", f"{repo_name}/{tag}"),
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "tag": tag,
                        "commit_sha": raw.get("commit_sha", ""),
                        "release_notes": raw.get("release_notes", ""),
                        "release_time": raw.get("release_time", ""),
                        "status": "released",
                        "release_type": classify_release_type(tag),
                        "author": raw.get("author", "") or "Unknown",
                        "author_email": raw.get("author_email", ""),
                        "tag_type": raw.get("tag_type", "release"),
                    }
                )

        self.set_shared_data("code_release_list", releases, "code_release")
        logger.info(
            "Fetched %s releases via %s adapter",
            len(releases),
            self.git_adapter.get_provider_name(),
        )
        return releases

    def validate_config(self) -> bool:
        return self.git_adapter.validate_config()
