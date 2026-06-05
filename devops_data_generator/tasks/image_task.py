#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像Task

从阿里云容器镜像服务(ACR)获取镜像标签信息
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


class ImageTask(BaseTask):
    """
    镜像Task，用于获取阿里云容器镜像服务(ACR)的镜像标签信息
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.instance_id = config.get('instance_id')
        self.region = config.get('region', 'cn-hangzhou')
        self.max_tags_per_repo = config.get('max_tags_per_repo', 0)
        self.client = None

        logger.info("ImageTask initialized with instance_id: %s, max_tags_per_repo: %s",
                     self.instance_id or "<missing>", self.max_tags_per_repo or "unlimited")
    
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
        获取镜像数据
        
        Returns:
            List[Dict[str, Any]]: 镜像列表
            
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
            
            # 从共享上下文获取镜像仓库数据
            registry_data = self.get_shared_data("image_registry_raw_data", [])
            if not registry_data:
                logger.warning("No image registry data found in shared context. Image task cannot proceed.")
                return []
            
            logger.info(f"Found {len(registry_data)} registries, fetching images...")
            
            all_images = []
            
            # 为每个仓库获取镜像标签
            for registry in registry_data:
                repo_id = self._extract_repo_id_from_registry(registry)
                if not repo_id:
                    logger.warning(f"Cannot extract repo_id from registry: {registry}")
                    continue
                
                images = self._list_repo_tags(repo_id, registry)
                all_images.extend(images)
            
            logger.info(f"Successfully fetched {len(all_images)} images from ACR API")
            # 存储到共享数据上下文
            self.set_shared_data("image_raw_data", all_images, "image_data")
            return all_images
            
        except Exception as e:
            error_msg = f"Error fetching image data: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _extract_repo_id_from_registry(self, registry: Dict[str, Any]) -> str:
        """
        从registry数据中提取repo_id
        
        Args:
            registry (Dict[str, Any]): 仓库数据
            
        Returns:
            str: repo_id，如果提取失败返回空字符串
        """
        # 尝试从registry_id中提取repo_id
        # registry_id格式: instance_id_namespace_repo_name
        return registry.get('registry_id', '')

    def _list_repo_tags(self, repo_id: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
        page_no = 1
        page_size = 100
        processed_images = []
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
                    image_data = self._process_image_data(tag, registry, repo_id)
                    if image_data:
                        processed_images.append(image_data)

                if len(tags) < page_size:
                    break
                if self.max_tags_per_repo and len(processed_images) >= self.max_tags_per_repo:
                    logger.info("Reached max_tags_per_repo=%s for repo %s, stopping", self.max_tags_per_repo, repo_id)
                    processed_images = processed_images[:self.max_tags_per_repo]
                    break
                page_no += 1

            logger.info("Retrieved %s tags for repo %s", len(processed_images), repo_id)
            return processed_images
        except Exception as e:
            logger.error("Error calling ListRepoTag API for repo %s: %s", repo_id, e)
            return processed_images
    
    def _process_image_data(self, tag: Any, registry: Dict[str, Any], repo_id: str) -> Dict[str, Any]:
        """
        处理单个镜像标签数据
        
        Args:
            tag: ACR镜像标签对象
            registry (Dict[str, Any]): 仓库信息
            repo_id (str): 仓库ID
            
        Returns:
            Dict[str, Any]: 处理后的镜像数据
        """
        try:
            # 构造镜像完整名称和URL
            registry_name = registry.get('registry_name', '')
            registry_namespace = registry.get('registry_namespace', '')
            tag_name = getattr(tag, 'tag', '')
            
            full_image_name = f"{registry.get('registry_name', '')}.{self.region}.cr.aliyuncs.com/{registry_namespace}/{registry_name}:{tag_name}"
            
            # 提取镜像数据
            image_data = {
                'image_id': getattr(tag, 'image_id'),
                'image_name': f"{registry_namespace}/{registry_name}" if registry_namespace else registry_name,
                'image_tag': getattr(tag, 'tag'),
                'image_digest': getattr(tag, 'digest'),
                'registry_id': registry.get('registry_id', ''),
                'full_image_name': full_image_name,
                'build_time': getattr(tag, 'image_update'),
                'size': getattr(tag, 'image_size', ''),
                'architecture': getattr(tag, 'image_size', 0),
                'os': getattr(tag, 'image_create', ''),
                'build_status': getattr(tag, 'status', ''),
            }
            
            return image_data
            
        except Exception as e:
            logger.warning(f"Error processing image data: {str(e)}")
            return {}
    
    def _build_image_url(self, registry: Dict[str, Any], tag: str) -> str:
        """
        构建镜像URL
        
        Args:
            registry (Dict[str, Any]): 仓库信息
            tag (str): 标签名
            
        Returns:
            str: 镜像URL
        """
        registry_url = registry.get('registry_url', '')
        if registry_url and tag:
            return f"{registry_url}:{tag}"
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
            List[str]: 依赖的task名称列表（依赖image_registry）
        """
        return ["image_registry"]
    
    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "image"
