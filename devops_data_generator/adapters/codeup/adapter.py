"""Codeup (Alibaba Cloud DevOps) implementation of IGitAdapter."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import IGitAdapter
from .client import (
    CODEUP_DEFAULT_ENDPOINT,
    CODEUP_SDK_AVAILABLE,
    create_codeup_client,
    devops_models,
    util_models,
)

logger = logging.getLogger(__name__)


class CodeupAdapter(IGitAdapter):
    """Codeup provider adapter (alibabacloud_devops20210625 SDK)."""

    # 值从 "aliyun" 改为 "codeup"（决策 D）；写入 user/repository 等记录的 data_source 字段。
    PROVIDER_NAME = "codeup"
    DEFAULT_BRANCH_FALLBACK = "master"

    # auth_mode controls how the adapter authenticates with Codeup:
    #   "ram"  — RAM AK/SK only; repos visible = those granted to the RAM user
    #   "pat"  — personal access token; repos visible = all the PAT owner can see
    #            (AK/SK still required for API request signing)
    SUPPORTED_AUTH_MODES = ("ram", "pat")

    def __init__(self, config: Dict[str, Any]):
        self.organization_id = config.get("organization_id", "")
        self.access_key_id = config.get("access_key_id", "")
        self.access_key_secret = config.get("access_key_secret", "")
        self.endpoint = config.get("endpoint") or CODEUP_DEFAULT_ENDPOINT

        self.auth_mode = (config.get("auth_mode") or "ram").lower()
        if self.auth_mode not in self.SUPPORTED_AUTH_MODES:
            logger.warning("Unknown auth_mode '%s', falling back to 'ram'", self.auth_mode)
            self.auth_mode = "ram"

        raw_token = config.get("access_token", "") or ""
        self.access_token = "" if raw_token.startswith("<") and raw_token.endswith(">") else raw_token

        if self.auth_mode == "pat" and not self.access_token:
            logger.warning("auth_mode=pat but access_token is empty; falling back to ram")
            self.auth_mode = "ram"

        if CODEUP_SDK_AVAILABLE and self.access_key_id and self.access_key_secret:
            self.client = create_codeup_client(self.access_key_id, self.access_key_secret, self.endpoint)
        else:
            self.client = None

    # ------------------------------------------------------------------
    # IGitAdapter implementation
    # ------------------------------------------------------------------
    def get_provider_name(self) -> str:
        return self.PROVIDER_NAME

    def get_default_branch_fallback(self) -> str:
        return self.DEFAULT_BRANCH_FALLBACK

    def validate_config(self) -> bool:
        if not CODEUP_SDK_AVAILABLE:
            logger.warning("alibabacloud-devops20210625 is not installed")
            return False
        if not self.organization_id:
            logger.error("Missing codeup organization_id")
            return False
        if not self.access_key_id or not self.access_key_secret:
            logger.error("Missing aliyun access_key credentials for codeup")
            return False
        return True

    def list_repositories(self, fetch_details: bool = True) -> List[Dict[str, Any]]:
        repositories: List[Dict[str, Any]] = []
        page = 1
        per_page = 100
        while True:
            req_kwargs = {
                "organization_id": self.organization_id,
                "page": page,
                "per_page": per_page,
            }
            if self.auth_mode == "pat" and self.access_token:
                req_kwargs["access_token"] = self.access_token
            request = devops_models.ListRepositoriesRequest(**req_kwargs)
            response = self.client.list_repositories_with_options(request, {}, util_models.RuntimeOptions())
            if response.status_code != 200 or not response.body:
                raise RuntimeError(f"codeup ListRepositories returned status {response.status_code}")

            result = response.body.result or []
            if not result:
                break

            for repo_data in result:
                repo_id = str(getattr(repo_data, "id", "") or "")
                name = getattr(repo_data, "name", "") or ""
                base = {
                    "repository_id": repo_id,
                    "name": name,
                    "full_path": getattr(repo_data, "path", "") or "",
                    "description": getattr(repo_data, "description", "") or "",
                    "owner_id": "",
                    "data_source": self.PROVIDER_NAME,
                    "platform_repo_id": repo_id,
                    "url": getattr(repo_data, "web_url", "") or "",
                    "default_branch": getattr(repo_data, "default_branch", "") or self.DEFAULT_BRANCH_FALLBACK,
                    "visibility": getattr(repo_data, "visibility_level", "") or "",
                    "language": "",
                    "language_breakdown": {},
                    "created_at": "",
                    "updated_at": "",
                }

                if fetch_details and base["repository_id"]:
                    try:
                        detail = self._get_repository_details(base["repository_id"])
                        base.update({k: v for k, v in detail.items() if v not in (None, "")})
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to fetch details for repo %s: %s", name, exc)
                repositories.append(base)

            if len(result) < per_page:
                break
            page += 1
        return repositories

    def list_repository_members(self, repo_id: str) -> List[Dict[str, Any]]:
        request = devops_models.ListRepositoryMemberWithInheritedRequest(
            organization_id=self.organization_id,
        )
        response = self.client.list_repository_member_with_inherited_with_options(
            repo_id, request, {}, util_models.RuntimeOptions()
        )
        if response.status_code != 200 or not response.body:
            logger.warning("codeup ListRepositoryMember returned %s for repo %s", response.status_code, repo_id)
            return []
        members: List[Dict[str, Any]] = []
        for member_data in response.body.result or []:
            user_id_raw = str(getattr(member_data, "id", "") or "")
            members.append(
                {
                    "user_id": f"{self.PROVIDER_NAME}:{user_id_raw}" if user_id_raw else "",
                    "full_name": getattr(member_data, "name", "") or getattr(member_data, "display_name", "") or "",
                    "email": getattr(member_data, "email", "") or "",
                    "display_name": getattr(member_data, "username", "")
                    or getattr(member_data, "login_name", "")
                    or "",
                    "avatar_url": getattr(member_data, "avatar_url", "") or "",
                    "data_source": self.PROVIDER_NAME,
                    "platform_user_id": user_id_raw,
                    "department": "",
                    "is_active": getattr(member_data, "state", "active") == "active",
                    "role": getattr(member_data, "role", "member") or "member",
                    # Codeup does not expose an access_level; fill 0 so the
                    # SLS schema matches the GitLab superset.
                    "access_level": getattr(member_data, "access_level", 0) or 0,
                }
            )
        return members

    def list_repository_releases(self, repo_id: str) -> List[Dict[str, Any]]:
        tags = self._list_repository_tags(repo_id)
        return [self._tag_to_release(repo_id, tag) for tag in tags if tag]

    def get_release_by_tag(self, repo_id: str, tag: str) -> Optional[Dict[str, Any]]:
        # Codeup does not expose a "get tag by name" API; degrade to list + filter.
        for release in self.list_repository_releases(repo_id):
            if release and release.get("tag_name") == tag:
                return release
        return None

    def list_pull_requests(self, repo_id: str) -> List[Dict[str, Any]]:
        """Return codeup merge requests for a repository in the unified pull_request schema.

        Uses ListMergeRequest (if available) on the alibabacloud-devops SDK; degrades
        to an empty list when the SDK lacks the call or returns nothing.
        """
        pull_requests: List[Dict[str, Any]] = []
        list_mr = getattr(self.client, "list_merge_request_with_options", None)
        if not list_mr:
            logger.debug("codeup SDK has no list_merge_request; skipping PR fetch for repo %s", repo_id)
            return pull_requests
        page = 1
        per_page = 100
        while True:
            request = devops_models.ListMergeRequest(
                organization_id=self.organization_id,
                page=page,
                per_page=per_page,
            )
            if self.auth_mode == "pat" and self.access_token:
                request.access_token = self.access_token
            try:
                response = list_mr(repo_id, request, {}, util_models.RuntimeOptions())
            except Exception as exc:  # noqa: BLE001
                logger.warning("codeup ListMergeRequest failed for repo %s: %s", repo_id, exc)
                break
            if response.status_code != 200 or not response.body:
                break
            result = response.body.result or []
            if not result:
                break
            for mr in result:
                pr_num = getattr(mr, "number", "") or getattr(mr, "id", "")
                pr_id_raw = str(pr_num)
                author_id = str(getattr(mr, "author_id", "") or "")
                pull_requests.append(
                    {
                        "pr_id": f"{self.PROVIDER_NAME}:{repo_id}!{pr_id_raw}" if pr_id_raw else "",
                        "project_id": "",
                        "repository_id": repo_id,
                        "number": pr_id_raw,
                        "title": getattr(mr, "title", "") or "",
                        "description": getattr(mr, "description", "") or "",
                        "author_id": f"{self.PROVIDER_NAME}:{author_id}" if author_id else "",
                        "source_branch": getattr(mr, "source_branch", "") or "",
                        "target_branch": getattr(mr, "target_branch", "") or "",
                        "status": self._map_mr_state(getattr(mr, "state", "")),
                        "data_source": self.PROVIDER_NAME,
                        "platform_pr_id": pr_id_raw,
                        "url": getattr(mr, "web_url", "") or "",
                        "created_at": getattr(mr, "created_at", "") or "",
                        "updated_at": getattr(mr, "updated_at", "") or "",
                        "merged_at": getattr(mr, "merge_commit_sha", "") and getattr(mr, "updated_at", "") or "",
                        "closed_at": "",
                    }
                )
            if len(result) < per_page:
                break
            page += 1
        return pull_requests

    @staticmethod
    def _map_mr_state(state: str) -> str:
        return {
            "open": "open",
            "opened": "open",
            "merged": "merged",
            "closed": "closed",
        }.get((state or "").lower(), "open")

    # ------------------------------------------------------------------
    # codeup-specific helpers
    # ------------------------------------------------------------------
    def _get_repository_details(self, repo_id: str) -> Dict[str, Any]:
        request = devops_models.GetRepositoryRequest(
            organization_id=self.organization_id,
            identity=repo_id,
        )
        response = self.client.get_repository_with_options(request, {}, util_models.RuntimeOptions())
        if response.status_code != 200 or not response.body:
            return {}
        detail = response.body.repository
        return {
            "description": getattr(detail, "description", "") or "",
            "url": getattr(detail, "web_url", "") or "",
            "language": getattr(detail, "language", "") or "",
            "default_branch": getattr(detail, "default_branch", "") or self.DEFAULT_BRANCH_FALLBACK,
        }

    def _list_repository_tags(self, repo_id: str) -> List[Dict[str, Any]]:
        page = 1
        per_page = 100
        tags: List[Dict[str, Any]] = []
        while True:
            request = devops_models.ListRepositoryTagsRequest(
                organization_id=self.organization_id,
                page=page,
                page_size=per_page,
            )
            response = self.client.list_repository_tags_with_options(
                repo_id, request, {}, util_models.RuntimeOptions()
            )
            if response.status_code != 200 or not response.body:
                break

            result = response.body.result or []
            if not result:
                break

            for tag_data in result:
                commit = getattr(tag_data, "commit", None)
                tags.append(
                    {
                        "tag_name": getattr(tag_data, "name", "") or "",
                        "commit_sha": getattr(commit, "id", "") if commit else "",
                        "message": getattr(commit, "message", "") if commit else "",
                        "created_at": getattr(tag_data, "created_at", "") or "",
                        "author_name": getattr(tag_data, "author_name", "") or "",
                        "author_email": getattr(tag_data, "author_email", "") or "",
                        "committer_name": getattr(commit, "committer_name", "") if commit else "",
                        "committer_email": getattr(commit, "committer_email", "") if commit else "",
                        "tagger_name": getattr(tag_data, "tagger_name", "") or "",
                        "tagger_email": getattr(tag_data, "tagger_email", "") or "",
                        "tag_type": getattr(tag_data, "type", "lightweight") or "lightweight",
                    }
                )

            if len(result) < per_page:
                break
            page += 1
        return tags

    def _tag_to_release(self, repo_id: str, tag: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tag_name = tag.get("tag_name") or ""
        if not tag_name:
            return None
        release_time = tag.get("created_at") or ""
        if release_time:
            try:
                release_time = datetime.fromisoformat(release_time.replace("Z", "+00:00")).isoformat()
            except (ValueError, AttributeError):
                pass
        author = tag.get("tagger_name") or tag.get("committer_name") or tag.get("author_name") or "Unknown"
        author_email = tag.get("tagger_email") or tag.get("committer_email") or tag.get("author_email") or ""
        return {
            "release_id": f"{self.PROVIDER_NAME}:{repo_id}/{tag_name}",
            "repository_id": repo_id,
            "name": tag_name,
            "version": tag_name.lstrip("v"),
            "description": tag.get("message", ""),
            "release_type": "",  # derived by release_classifier in the task
            "status": "completed",
            "data_source": self.PROVIDER_NAME,
            "platform_release_id": f"{repo_id}/{tag_name}",
            "url": "",
            "created_by": author,
            "tag_name": tag_name,
            "target_commitish": "",
            "commit_sha": tag.get("commit_sha", ""),
            "release_time": release_time,
            "tag_type": tag.get("tag_type", "lightweight"),
        }
