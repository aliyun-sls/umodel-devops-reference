#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像仓库Task

从阿里云容器镜像服务(ACR)获取镜像仓库信息
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


class ImageRegistryTask(BaseTask):
    """
    镜像仓库Task，用于获取阿里云容器镜像服务(ACR)的仓库信息
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化镜像仓库Task
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.instance_id = config.get('instance_id')
        self.region = config.get('region', 'cn-hangzhou')
        self.max_repositories = config.get('max_repositories', 0)
        self.client = None

        logger.info("ImageRegistryTask initialized with instance_id: %s, max_repositories: %s",
                     self.instance_id or "<missing>", self.max_repositories or "unlimited")
    
    def _create_client(self):
        """
        创建阿里云容器镜像服务客户端
        
        Returns:
            Cr20181201Client: ACR客户端
        """
        try:
            # 使用统一凭证客户端
            creConfig = credentialConfig(
                type='access_key',
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret
            )
            credential = CredentialClient(creConfig)
            config = open_api_models.Config(
                credential=credential
            )
            
            # 设置服务端点
            config.endpoint = f'cr.{self.region}.aliyuncs.com'
            
            client = Cr20181201Client(config)
            logger.info(f"Successfully created ACR client for region: {self.region}")
            return client
            
        except Exception as e:
            logger.error(f"Error creating ACR client: {str(e)}")
            raise RuntimeError(f"Failed to create ACR client: {str(e)}") from e
    
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取镜像仓库数据
        
        Returns:
            List[Dict[str, Any]]: 镜像仓库列表
            
        Raises:
            ValueError: 配置验证失败
            RuntimeError: API调用失败
        """
        if not self.validate_config():
            error_msg = "Configuration validation failed"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # 创建客户端
            if not self.client:
                self.client = self._create_client()
            
            logger.info(f"Fetching repositories from ACR instance: {self.instance_id}")
            
            # 获取仓库列表
            repositories = self._list_repositories()
            
            # 处理仓库数据
            processed_repositories = []
            for repo in repositories:
                repo_data = self._process_repository_data(repo)
                if repo_data:
                    processed_repositories.append(repo_data)
            
            logger.info(f"Successfully fetched {len(processed_repositories)} repositories from ACR API")
            self.set_shared_data("image_registry_raw_data", processed_repositories, "image_registry_data")
            return processed_repositories
            
        except Exception as e:
            error_msg = f"Error fetching repository data: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _list_repositories(self) -> List[Any]:
        """
        获取仓库列表
        
        Returns:
            List[Any]: ACR仓库列表
            
        Raises:
            RuntimeError: API调用失败
        """
        page_no = 1
        page_size = 100
        all_repos = []
        try:
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
                    all_repos = all_repos[:self.max_repositories]
                    logger.info("Reached max_repositories=%s, stopping", self.max_repositories)
                    break
                page_no += 1

            logger.info("Retrieved %s repositories from API", len(all_repos))
            return all_repos
        except Exception as e:
            logger.error("Error calling ListRepository API: %s", e)
            raise RuntimeError(f"Failed to list repositories: {e}") from e
    
    def _process_repository_data(self, repo: Any) -> Dict[str, Any]:
        """
        处理单个仓库数据
        
        Args:
            repo: ACR仓库对象
            
        Returns:
            Dict[str, Any]: 处理后的仓库数据
        """
        try:

            registry_url = f"https://cr.console.aliyun.com/repository/{self.region}/{self.instance_id}/{getattr(repo, 'repo_namespace_name', '')}/{getattr(repo, 'repo_name', '')}/details"
            is_public = 'PRIVATE' if getattr(repo, 'repo_type', 'PRIVATE') == 'PRIVATE' else 'PUBLIC'

            # 提取仓库基本信息
            repo_data = {
                'registry_id': getattr(repo, 'repo_id', self.instance_id),
                'registry_name': getattr(repo, 'repo_name', ''),
                "registry_url": registry_url,
                'description': getattr(repo, 'description', ''),
                'registry_namespace': getattr(repo, 'repo_namespace_name', ''),
                'region': self.region,
                'is_public': is_public,
                'instance_id': self.instance_id
            }

            
            
            return repo_data
            
        except Exception as e:
            logger.warning(f"Error processing repository data: {str(e)}")
            return {}
    
    def _build_registry_url(self, namespace: str, repo_name: str) -> str:
        """
        构建镜像仓库URL
        
        Args:
            namespace (str): 命名空间
            repo_name (str): 仓库名称
            
        Returns:
            str: 仓库URL
        """
        if namespace and repo_name:
            return f"{self.instance_id}.registry.{self.region}.cr.aliyuncs.com/{namespace}/{repo_name}"
        return ""
    
    def validate_config(self) -> bool:
        """
        验证配置

        Returns:
            bool: 配置是否有效
        """
        if not ACR_SDK_AVAILABLE:
            logger.warning("ACR SDK dependencies are not installed")
            return False

        if not self.access_key_id or not self.access_key_secret:
            logger.warning("ACR access key is not configured")
            return False

        if not self.instance_id:
            logger.warning("ACR instance_id is not configured")
            return False
            
        logger.info(f"Config validation passed for instance_id: {self.instance_id}")
        return True
    
    def get_dependencies(self) -> List[str]:
        """
        获取task依赖列表
        
        Returns:
            List[str]: 依赖的task名称列表（镜像仓库任务无依赖）
        """
        return []
    
    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "image_registry"
