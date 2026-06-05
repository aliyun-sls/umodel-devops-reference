#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pod 使用镜像关系任务

基于 Kubernetes Pod 数据和镜像数据，生成 k8s.pod_uses_devops.image 关系。
依赖于 kubernetes_pod 和 image 任务提供的数据。
"""

import hashlib
import logging
from typing import Dict, List, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class PodUsesImageTask(BaseTask):
    """
    Pod 使用镜像关系生成任务
    
    基于 Pod 容器镜像信息和镜像数据，自动生成 uses 关系。
    依赖于 kubernetes_pod 和 image 任务提供的数据。
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Pod 使用镜像关系任务
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.task_type = 'relationship'  # 这是一个关系任务
        logger.info("PodUsesImageTask initialized")
    
    def get_dependencies(self) -> List[str]:
        """
        声明依赖关系：依赖于 kubernetes_pod 和 image 任务
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        return ["kubernetes_pod", "image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取 Pod 使用镜像的关系数据
        
        基于 Pod 容器镜像信息和镜像数据，生成 uses 关系数据。
        
        Returns:
            List[Dict[str, Any]]: 关系数据列表
            
        Raises:
            RuntimeError: 数据获取失败
        """
        try:
            # 从共享上下文获取所需数据
            pods = self.get_shared_data("k8s_pod_raw_data", [])
            images = self.get_shared_data("image_raw_data", [])
            
            if not pods:
                logger.warning("No pod data found in shared context")
                return []
            
            if not images:
                logger.warning("No image data found in shared context")
                return []
            
            logger.info(f"Processing relationships: {len(pods)} pods, {len(images)} images")
            
            # 构建镜像查找索引，支持多种镜像匹配方式
            image_lookup = self._build_image_lookup(images)
            
            # 生成关系数据
            relationships = []
            
            # 为每个 Pod 的每个容器镜像查找对应的镜像实体
            for pod in pods:
                pod_images = pod.get('images', [])
                pod_id = pod.get('pod_id', '')
                
                if not pod_images or not pod_id:
                    logger.debug(f"Pod {pod_id} has no images or missing pod_id")
                    continue
                
                # 处理 Pod 中的每个镜像
                for container_image in pod_images:
                    matching_image = self._find_matching_image(container_image, image_lookup)
                    
                    if matching_image:
                        relationship = self._create_relationship(pod, matching_image, container_image)
                        if relationship:
                            relationships.append(relationship)
                    else:
                        logger.debug(f"No matching image entity found for container image: {container_image}")
            
            # 存储关系数据到共享上下文
            self.set_shared_data("pod_uses_image_list", relationships, "relationship_data")
            logger.info(f"Stored {len(relationships)} pod-image relationships to shared context")
            
            logger.info(f"Generated {len(relationships)} pod_uses_image relationships")
            return relationships
            
        except Exception as e:
            error_msg = f"Error generating pod-image relationships: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _build_image_lookup(self, images: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        构建镜像查找索引
        
        Args:
            images (List[Dict[str, Any]]): 镜像数据列表
            
        Returns:
            Dict[str, Dict[str, Any]]: 镜像查找索引，支持多种匹配方式
        """
        image_lookup = {}
        
        for image in images:
            image_name = image.get('image_name', '')
            tag = image.get('tag', '') or image.get('image_tag', '')
            registry_id = image.get('registry_id', '')
            
            if not image_name:
                continue
            
            # 构建多种可能的镜像标识符用于匹配
            possible_identifiers = []
            
            # 1. 完整的镜像名称:标签
            if tag:
                possible_identifiers.extend([
                    f"{image_name}:{tag}",
                    f"{image_name.split('/')[-1]}:{tag}",  # 只用镜像名部分
                ])
            
            # 2. 只有镜像名称
            possible_identifiers.extend([
                image_name,
                image_name.split('/')[-1],  # 只用镜像名部分
            ])
            
            # 3. 基于 registry_id 的匹配（如果有的话）
            if registry_id:
                possible_identifiers.append(registry_id)
            
            # 将所有可能的标识符都映射到这个镜像
            for identifier in possible_identifiers:
                if identifier:
                    image_lookup[identifier] = image
        
        logger.debug(f"Built image lookup with {len(image_lookup)} identifiers for {len(images)} images")
        return image_lookup

    def _find_matching_image(self, container_image: str, image_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        查找匹配的镜像实体
        
        Args:
            container_image (str): 容器镜像字符串 (如: "registry.cn-hangzhou.cr.aliyuncs.com/apm-demo/mymall-order:v1.0.0")
            image_lookup (Dict[str, Dict[str, Any]]): 镜像查找索引
            
        Returns:
            Dict[str, Any]: 匹配的镜像实体，如果未找到返回None
        """
        if not container_image:
            return None
        
        # 尝试多种匹配策略
        possible_matches = [
            # 1. 完全匹配
            container_image,
            
            # 2. 提取镜像名和标签
            container_image.split('/')[-1] if '/' in container_image else container_image,
            
            # 3. 如果包含标签，分别尝试匹配
            container_image.split(':')[0] if ':' in container_image else None,
            container_image.split('/')[-1].split(':')[0] if '/' in container_image and ':' in container_image else None,
        ]
        
        # 过滤空值
        possible_matches = [match for match in possible_matches if match]
        
        # 尝试每种匹配方式
        for match_key in possible_matches:
            if match_key in image_lookup:
                logger.debug(f"Found matching image for '{container_image}' using key '{match_key}'")
                return image_lookup[match_key]
        
        # 如果直接匹配失败，尝试模糊匹配（基于镜像名称）
        container_image_name = self._extract_image_name(container_image)
        
        for lookup_key, image in image_lookup.items():
            lookup_image_name = self._extract_image_name(lookup_key)
            
            if container_image_name and lookup_image_name:
                if container_image_name == lookup_image_name:
                    logger.debug(f"Found matching image for '{container_image}' using fuzzy match on name '{container_image_name}'")
                    return image
        
        return None

    def _extract_image_name(self, full_image: str) -> str:
        """
        从完整镜像路径中提取镜像名称
        
        Args:
            full_image (str): 完整镜像路径
            
        Returns:
            str: 镜像名称
        """
        if not full_image:
            return ""
        
        # 移除标签
        image_without_tag = full_image.split(':')[0]
        
        # 提取最后一部分作为镜像名称
        image_name = image_without_tag.split('/')[-1]
        
        return image_name

    def _create_relationship(self, pod: Dict[str, Any], image: Dict[str, Any], container_image: str) -> Dict[str, Any]:
        """
        创建 Pod 使用镜像的关系数据
        
        Args:
            pod (Dict[str, Any]): Pod 数据
            image (Dict[str, Any]): 镜像数据
            container_image (str): 容器镜像字符串
            
        Returns:
            Dict[str, Any]: 关系数据
        """
        try:
            # 生成实体ID（使用MD5哈希）
            pod_entity_id = pod.get('entity_id', pod.get('pod_id', ''))
            image_entity_id = self._generate_entity_id(image, 'image')
            
            # 构建关系数据
            relationship_data = {
                '__relation_type__': 'uses',
                '__src_domain__': 'k8s',
                '__src_entity_type__': 'k8s.pod',
                '__src_entity_id__': pod_entity_id,
                '__dest_domain__': 'devops',
                '__dest_entity_type__': 'devops.image',
                '__dest_entity_id__': image_entity_id,
                
                # 关系属性
                'pod_id': pod.get('pod_id', ''),
                'image_id': image.get('image_id', ''),
                'image_name': image.get('image_name', ''),
                'image_tag': image.get('tag', '') or image.get('image_tag', ''),
                'container_image': container_image,
                'namespace': pod.get('namespace', ''),
                'container_count': pod.get('container_count', 0),
                'priority': 5,  # 来自UModel定义
                'relationship_source': 'container_spec',
                'uses_type': 'container_runtime'
            }
            
            return relationship_data
            
        except Exception as e:
            logger.error(f"Error creating relationship: {str(e)}")
            return {}
    
    def _generate_entity_id(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        生成实体ID（与data_mapping.yaml中的规则保持一致）
        
        Args:
            entity (Dict[str, Any]): 实体数据
            entity_type (str): 实体类型
            
        Returns:
            str: 生成的实体ID
        """
        try:
            # 定义不同实体类型的主键字段
            entity_primary_keys_mapping = {
                'image': ['image_id'],
                'pod': ['pod_id'],
            }
            
            primary_keys = entity_primary_keys_mapping.get(entity_type, ['id'])
            
            if not primary_keys:
                # 如果没有定义主键，使用常见的ID字段
                fallback_id = entity.get('entity_id', entity.get('id', ''))
                return str(fallback_id) if fallback_id else ''
            
            # 获取主键值
            primary_key_values = []
            for key in primary_keys:
                value = entity.get(key, '')
                if not value:
                    logger.debug(f"Primary key '{key}' not found in entity data for type '{entity_type}'")
                primary_key_values.append(str(value))
            
            # 生成MD5哈希
            primary_key_string = '|'.join(primary_key_values)
            if primary_key_string:
                entity_id = hashlib.md5(primary_key_string.encode('utf-8')).hexdigest()
            else:
                entity_id = str(entity.get('entity_id', entity.get('id', '')))
            
            logger.debug(f"Generated entity ID '{entity_id}' for type '{entity_type}' using keys {primary_keys}")
            return entity_id
            
        except Exception as e:
            logger.error(f"Error generating entity ID for type '{entity_type}': {str(e)}")
            return str(entity.get('entity_id', entity.get('id', '')))

    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 配置是否有效
        """
        # Pod 使用镜像关系不需要额外配置，直接返回True
        return True

    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "pod_uses_image"
