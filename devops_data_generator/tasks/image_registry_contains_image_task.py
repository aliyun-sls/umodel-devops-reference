#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像仓库包含镜像关系任务

基于镜像仓库和镜像数据，生成 devops.image_registry_contains_devops.image 关系。
依赖于 image_registry 和 image 任务提供的数据。
"""

import hashlib
import logging
from typing import Dict, List, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ImageRegistryContainsImageTask(BaseTask):
    """
    镜像仓库包含镜像关系生成任务
    
    基于镜像仓库和镜像数据，自动生成 contains 关系。
    依赖于 image_registry 和 image 任务提供的数据。
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化镜像仓库包含镜像关系任务
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.task_type = 'relationship'  # 这是一个关系任务
        logger.info("ImageRegistryContainsImageTask initialized")
    
    def get_dependencies(self) -> List[str]:
        """
        声明依赖关系：依赖于 image_registry 和 image 任务
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        return ["image_registry", "image"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取镜像仓库包含镜像的关系数据
        
        基于镜像仓库和镜像数据，通过 registry_id 字段进行关联，
        生成 contains 关系数据。
        
        Returns:
            List[Dict[str, Any]]: 关系数据列表
            
        Raises:
            RuntimeError: 数据获取失败
        """
        try:
            # 从共享上下文获取镜像仓库数据
            image_registries = self.get_shared_data("image_registry_raw_data", [])
            if not image_registries:
                logger.warning("No image registry data found in shared context")
                return []
            
            # 从共享上下文获取镜像数据
            images = self.get_shared_data("image_raw_data", [])
            if not images:
                logger.warning("No image data found in shared context")
                return []
            
            logger.info(f"Processing relationships: {len(image_registries)} registries, {len(images)} images")
            
            # 生成关系数据
            relationships = []
            
            # 为每个镜像查找对应的镜像仓库
            for image in images:
                image_registry_id = image.get('registry_id', '')
                if not image_registry_id:
                    logger.debug(f"Image {image.get('image_id', 'unknown')} missing registry_id")
                    continue
                
                # 查找匹配的镜像仓库
                matching_registry = self._find_registry_by_id(image_registries, image_registry_id)
                if not matching_registry:
                    logger.debug(f"No registry found for registry_id: {image_registry_id}")
                    continue
                
                # 创建关系
                relationship = self._create_relationship(matching_registry, image)
                if relationship:
                    relationships.append(relationship)
            
            # 存储关系数据到共享上下文
            self.set_shared_data("image_registry_contains_image_list", relationships, "relationship_data")
            logger.info(f"Stored {len(relationships)} image-registry relationships to shared context")
            
            logger.info(f"Generated {len(relationships)} image_registry_contains_image relationships")
            return relationships
            
        except Exception as e:
            error_msg = f"Error generating image-registry relationships: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _find_registry_by_id(self, registries: List[Dict[str, Any]], registry_id: str) -> Dict[str, Any]:
        """
        根据镜像仓库ID查找镜像仓库数据
        
        Args:
            registries (List[Dict[str, Any]]): 镜像仓库数据列表
            registry_id (str): 镜像仓库ID
            
        Returns:
            Dict[str, Any]: 镜像仓库数据，如果未找到返回None
        """
        for registry in registries:
            if registry.get('registry_id') == registry_id:
                return registry
        return None

    def _create_relationship(self, registry: Dict[str, Any], image: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建镜像仓库包含镜像的关系数据
        
        Args:
            registry (Dict[str, Any]): 镜像仓库数据
            image (Dict[str, Any]): 镜像数据
            
        Returns:
            Dict[str, Any]: 关系数据
        """
        try:
            # 生成实体ID（使用MD5哈希）
            registry_entity_id = self._generate_entity_id(registry, 'image_registry')
            image_entity_id = self._generate_entity_id(image, 'image')
            
            # 构建关系数据
            relationship_data = {
                '__relation_type__': 'contains',
                '__src_domain__': 'devops',
                '__src_entity_type__': 'devops.image_registry',
                '__src_entity_id__': registry_entity_id,
                '__dest_domain__': 'devops',
                '__dest_entity_type__': 'devops.image',
                '__dest_entity_id__': image_entity_id,
                
                # 关系属性
                'registry_name': registry.get('repository_name', ''),
                'registry_id': registry.get('registry_id', ''),
                'image_name': image.get('image_name', ''),
                'image_tag': image.get('tag', ''),
                'image_id': image.get('image_id', ''),
                'priority': 5,  # 来自UModel定义
                'relationship_source': 'auto_generated',
                'contains_type': 'image_storage'
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
                'image_registry': ['registry_id'],
                'image': ['image_id'],
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
        # 镜像仓库包含镜像关系不需要额外配置，直接返回True
        return True

    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "image_registry_contains_image"
