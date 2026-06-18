#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker Image Task

From Alibaba Cloud Container Registry (ACR): enumerate repositories, list
image tags, and produce docker_image records. Per decision B, every ACR
fetch also produces a paired ``artifact`` record (the abstract build
artifact) plus enough context for the ``artifact_same_as_docker_image``
relation to be derived downstream.

The image_registry entity has been removed (decision A); the ACR
ListRepository enumeration that previously lived in ImageRegistryTask is
folded into this task.
"""

import logging
from typing import List, Dict, Any

try:
    from alibabacloud_cr20181201.client import Client as Cr20181201Client
    from alibabacloud_credentials.client import Client as CredentialClient
    from alibabacloud_credentials.client import Config as credentialConfig
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_cr20181201 import models as cr_20181201_models
    from alibabacloud_tea_util import models as util_models
    ACR_SDK_AVAILABLE = True
except ModuleNotFoundError:
    Cr20181201Client = None
    CredentialClient = None
    credentialConfig = None
    open_api_models = None
    cr_20181201_models = None
    util_models = None
    ACR_SDK_AVAILABLE = False

from .base_task import BaseTask

logger = logging.getLogger(__name__)

ACR_DATA_SOURCE = "aliyun_acr"  # Alibaba Cloud Container Registry (ACR), distinct from harbor


class DockerImageTask(BaseTask):
    """Docker image task — enumerates ACR repos/tags and emits docker_image
    (plus paired artifact records, decision B)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.instance_id = config.get('instance_id')
        self.region = config.get('region', 'cn-hangzhou')
        self.max_repositories = config.get('max_repositories', 0)
        self.max_tags_per_repo = config.get('max_tags_per_repo', 0)
        self.client = None
        logger.info(
            "DockerImageTask initialized with instance_id: %s, max_repositories: %s, max_tags_per_repo: %s",
            self.instance_id or "<missing>",
            self.max_repositories or "unlimited",
            self.max_tags_per_repo or "unlimited",
        )

    def _create_client(self):
        try:
            cre_config = credentialConfig(
                type='access_key',
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
            )
            credential = CredentialClient(cre_config)
            config = open_api_models.Config(credential=credential)
            config.endpoint = f'cr.{self.region}.aliyuncs.com'
            client = Cr20181201Client(config)
            logger.info("Successfully created ACR client for region: %s", self.region)
            return client
        except Exception as e:
            logger.error("Error creating ACR client: %s", e)
            raise RuntimeError(f"Failed to create ACR client: {e}") from e

    def fetch_data(self) -> List[Dict[str, Any]]:
        if not self.validate_config():
            raise ValueError("Configuration validation failed")

        try:
            if not self.client:
                self.client = self._create_client()

            acr_repos = self._list_repositories()
            logger.info("Found %s ACR repositories, fetching image tags...", len(acr_repos))

            all_images: List[Dict[str, Any]] = []
            all_artifacts: List[Dict[str, Any]] = []
            for repo in acr_repos:
                repo_id = str(getattr(repo, 'repo_id', '') or '')
                repo_name = getattr(repo, 'repo_name', '') or ''
                repo_namespace = getattr(repo, 'repo_namespace_name', '') or ''
                if not repo_id:
                    logger.warning("ACR repo without repo_id, skipping: %s/%s", repo_namespace, repo_name)
                    continue
                images, artifacts = self._list_repo_tags(repo, repo_id)
                all_images.extend(images)
                all_artifacts.extend(artifacts)

            self.set_shared_data("docker_image_raw_data", all_images, "docker_image")
            self.set_shared_data("artifact_raw_data", all_artifacts, "artifact")
            logger.info(
                "Fetched %s docker_images and %s paired artifacts from ACR",
                len(all_images),
                len(all_artifacts),
            )
            # Return docker_image records; artifact records are consumed via the
            # shared-context key by a thin artifact_task wrapper if registered.
            return all_images
        except Exception as e:
            logger.error("Error fetching docker image data: %s", e)
            raise RuntimeError(f"Error fetching docker image data: {e}") from e

    def _list_repositories(self) -> List[Any]:
        page_no = 1
        page_size = 100
        all_repos: List[Any] = []
        while True:
            request = cr_20181201_models.ListRepositoryRequest(
                instance_id=self.instance_id,
                page_no=page_no,
                page_size=page_size,
            )
            response = self.client.list_repository_with_options(request, util_models.RuntimeOptions())
            if response.status_code != 200 or not response.body:
                logger.warning("ListRepository API returned status %s", response.status_code)
                break
            repos = response.body.repositories or []
            all_repos.extend(repos)
            if len(repos) < page_size:
                break
            if self.max_repositories and len(all_repos) >= self.max_repositories:
                all_repos = all_repos[: self.max_repositories]
                logger.info("Reached max_repositories=%s, stopping", self.max_repositories)
                break
            page_no += 1
        return all_repos

    def _list_repo_tags(self, repo: Any, repo_id: str) -> tuple:
        repo_name = getattr(repo, 'repo_name', '') or ''
        repo_namespace = getattr(repo, 'repo_namespace_name', '') or ''
        registry = f"{self.instance_id}.{self.region}.cr.aliyuncs.com"
        images: List[Dict[str, Any]] = []
        artifacts: List[Dict[str, Any]] = []
        page_no = 1
        page_size = 100
        try:
            while True:
                request = cr_20181201_models.ListRepoTagRequest(
                    repo_id=repo_id,
                    instance_id=self.instance_id,
                    page_no=page_no,
                    page_size=page_size,
                )
                response = self.client.list_repo_tag_with_options(request, util_models.RuntimeOptions())
                if response.status_code != 200 or not response.body:
                    logger.warning("ListRepoTag returned status %s for repo %s", response.status_code, repo_id)
                    break
                tags = response.body.images or []
                for tag in tags:
                    image, artifact = self._process_tag(tag, registry, repo_namespace, repo_name, repo_id)
                    if image:
                        images.append(image)
                    if artifact:
                        artifacts.append(artifact)
                if len(tags) < page_size:
                    break
                if self.max_tags_per_repo and len(images) >= self.max_tags_per_repo:
                    images = images[: self.max_tags_per_repo]
                    artifacts = artifacts[: self.max_tags_per_repo]
                    break
                page_no += 1
        except Exception as e:  # noqa: BLE001
            logger.error("Error calling ListRepoTag API for repo %s: %s", repo_id, e)
        return images, artifacts

    def _process_tag(self, tag: Any, registry: str, repo_namespace: str, repo_name: str, repo_id: str) -> tuple:
        try:
            tag_value = getattr(tag, 'tag', '') or ''
            digest = getattr(tag, 'digest', '') or ''
            platform_image_id = str(getattr(tag, 'image_id', '') or repo_id)
            docker_image_id = f"{ACR_DATA_SOURCE}:{platform_image_id}:{tag_value}" if platform_image_id else ""
            artifact_id = f"{ACR_DATA_SOURCE}:{platform_image_id}:artifact:{tag_value}" if platform_image_id else ""
            image_repo_path = f"{repo_namespace}/{repo_name}" if repo_namespace else repo_name
            full_image_name = f"{registry}/{image_repo_path}:{tag_value}"
            created_at = getattr(tag, 'image_update', '') or getattr(tag, 'create_time', '') or ''
            # D12 fix: architecture/os must take correct fields, not image_size/image_create.
            architecture = getattr(tag, 'architecture', '') or getattr(tag, 'os_arch', '') or ''
            os_name = getattr(tag, 'os', '') or getattr(tag, 'os_name', '') or ''

            image = {
                'docker_image_id': docker_image_id,
                'artifact_id': artifact_id,
                'registry': registry,
                'repository': image_repo_path,
                'tag': tag_value,
                'digest': digest,
                'full_image_name': full_image_name,
                'base_image': '',
                'platform': '',
                'architecture': architecture,
                'os': os_name,
                'data_source': ACR_DATA_SOURCE,
                'platform_image_id': platform_image_id,
                'created_at': created_at,
            }
            artifact = {
                'artifact_id': artifact_id,
                'name': repo_name,
                'version': tag_value.lstrip('v'),
                'artifact_type': 'docker_image',
                'repository_id': '',
                'commit_sha': '',
                'tag_name': tag_value,
                'pipeline_run_id': '',
                'storage_location': full_image_name,
                'data_source': ACR_DATA_SOURCE,
                'platform_artifact_id': platform_image_id,
                'url': '',
                'created_at': created_at,
                'created_by': '',
            }
            return image, artifact
        except Exception as e:  # noqa: BLE001
            logger.warning("Error processing image tag: %s", e)
            return {}, {}

    def validate_config(self) -> bool:
        if not ACR_SDK_AVAILABLE:
            logger.warning("ACR SDK dependencies are not installed")
            return False
        if not self.access_key_id or not self.access_key_secret:
            logger.warning("ACR access key is not configured")
            return False
        if not self.instance_id:
            logger.warning("ACR instance_id is not configured")
            return False
        return True

    def get_dependencies(self) -> List[str]:
        return []

    def get_task_name(self) -> str:
        return "docker_image"
