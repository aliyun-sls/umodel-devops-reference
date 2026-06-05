#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像来源于代码发布关系任务

基于代码仓库与镜像仓库映射关系以及标签匹配，生成 devops.image_sourced_from_devops.code_release 关系。
依赖于 image, code_release, code_repository, image_registry 任务提供的数据。
"""

import hashlib
import logging
import os
import re
import yaml
from typing import Dict, List, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class ImageSourcedFromCodeReleaseTask(BaseTask):
    """
    镜像来源于代码发布关系生成任务
    
    基于映射配置和标签匹配，自动生成镜像与代码发布之间的 sourced_from 关系。
    依赖于 image, code_release, code_repository, image_registry 任务提供的数据。
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化镜像来源于代码发布关系任务
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.task_type = 'relationship'  # 这是一个关系任务
        
        # 加载映射配置文件
        self.mapping_config = self._load_mapping_config()
        logger.info("ImageSourcedFromCodeReleaseTask initialized")
    
    def get_dependencies(self) -> List[str]:
        """
        声明依赖关系：依赖于 image, code_release, code_repository, image_registry 任务
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        return ["image", "code_release", "code_repository", "image_registry"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取镜像来源于代码发布的关系数据
        
        基于映射配置和标签匹配规则，生成 sourced_from 关系数据。
        
        Returns:
            List[Dict[str, Any]]: 关系数据列表
            
        Raises:
            RuntimeError: 数据获取失败
        """
        try:
            # 从共享上下文获取所需数据
            images = self.get_shared_data("image_raw_data", [])
            code_releases = self.get_shared_data("code_release_list", [])
            code_repositories = self.get_shared_data("code_repos", [])
            image_registries = self.get_shared_data("image_registry_raw_data", [])
            
            if not images:
                logger.warning("No image data found in shared context")
                return []
            
            if not code_releases:
                logger.warning("No code_release data found in shared context")
                return []
            
            if not code_repositories:
                logger.warning("No code_repository data found in shared context")
                return []
                
            if not image_registries:
                logger.warning("No image_registry data found in shared context")
                return []
            
            logger.info(f"Processing relationships: {len(images)} images, {len(code_releases)} code releases")
            
            # 构建查找索引
            repo_lookup = {repo.get('repo_name', ''): repo for repo in code_repositories}
            registry_lookup = {reg.get('registry_id', ''): reg for reg in image_registries}
            
            # 获取映射关系
            repo_image_mappings = self.mapping_config.get('repo_image_mappings', {})
            tag_matching_config = self.mapping_config.get('tag_matching_rules', {})
            
            # 生成关系数据
            relationships = []
            
            # 为每个镜像查找对应的代码发布
            for image in images:
                image_registry_id = image.get('registry_id', '')
                image_tag = image.get('image_tag', '')
                
                if not image_registry_id or not image_tag:
                    logger.debug(f"Image {image.get('image_id', 'unknown')} missing registry_id or tag")
                    continue
                
                # 根据映射关系找到对应的代码仓库
                matching_repo_name = self._find_repo_by_registry_id(repo_image_mappings, image_registry_id)
                if not matching_repo_name:
                    logger.debug(f"No repository mapping found for registry_id: {image_registry_id}")
                    continue
                
                # 查找匹配的代码发布
                matching_releases = self._find_matching_code_releases(
                    code_releases, matching_repo_name, image_tag, tag_matching_config
                )
                
                # 为每个匹配的发布创建关系
                for code_release in matching_releases:
                    relationship = self._create_relationship(image, code_release)
                    if relationship:
                        relationships.append(relationship)
            
            # 存储关系数据到共享上下文
            self.set_shared_data("image_sourced_from_code_release_list", relationships, "relationship_data")
            logger.info(f"Stored {len(relationships)} image-code-release relationships to shared context")
            
            logger.info(f"Generated {len(relationships)} image_sourced_from_code_release relationships")
            return relationships
            
        except Exception as e:
            error_msg = f"Error generating image-code-release relationships: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _load_mapping_config(self) -> Dict[str, Any]:
        """
        加载映射配置文件
        
        Returns:
            Dict[str, Any]: 映射配置数据
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        try:
            # 获取配置文件路径
            config_dir = getattr(self, 'config_dir', None)
            if not config_dir:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                config_dir = os.path.join(os.path.dirname(current_dir), 'config')
            config_path = os.path.join(config_dir, 'repo_image_mapping.yaml')
            
            if not os.path.exists(config_path):
                # 如果配置文件不存在，使用默认配置
                logger.warning(f"Mapping config file not found: {config_path}, using default config")
                return {
                    'repo_image_mappings': {},
                    'tag_matching_rules': {'match_type': 'exact'},
                    'relationship_config': {'strict_mapping': False}
                }
            
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            if not config:
                logger.warning("Empty mapping config file, using default config")
                return {
                    'repo_image_mappings': {},
                    'tag_matching_rules': {'match_type': 'exact'},
                    'relationship_config': {'strict_mapping': False}
                }
            
            logger.info(f"Loaded mapping config from: {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading mapping config: {str(e)}")
            # 返回默认配置
            return {
                'repo_image_mappings': {},
                'tag_matching_rules': {'match_type': 'exact'},
                'relationship_config': {'strict_mapping': False}
            }

    def _find_repo_by_registry_id(self, mappings: Dict[str, str], registry_id: str) -> str:
        """
        根据镜像仓库ID找到对应的代码仓库名称
        
        Args:
            mappings (Dict[str, str]): 代码仓库到镜像仓库的映射关系
            registry_id (str): 镜像仓库ID
            
        Returns:
            str: 代码仓库名称，如果未找到返回空字符串
        """
        for repo_name, mapped_registry_id in mappings.items():
            if mapped_registry_id == registry_id:
                return repo_name
        return ""

    def _find_matching_code_releases(
        self, 
        code_releases: List[Dict[str, Any]], 
        repo_name: str, 
        image_tag: str, 
        tag_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        查找匹配的代码发布
        
        Args:
            code_releases (List[Dict[str, Any]]): 代码发布数据列表
            repo_name (str): 代码仓库名称
            image_tag (str): 镜像标签
            tag_config (Dict[str, Any]): 标签匹配配置
            
        Returns:
            List[Dict[str, Any]]: 匹配的代码发布列表
        """
        matching_releases = []
        match_type = tag_config.get('match_type', 'exact')
        tag_transformations = tag_config.get('tag_transformations', [])
        
        for release in code_releases:
            release_repo_name = release.get('repo_name', '')
            release_tag = release.get('tag', '')
            
            # 检查仓库名称是否匹配
            if release_repo_name != repo_name:
                continue
            
            # 检查标签是否匹配
            if self._tags_match(release_tag, image_tag, match_type, tag_transformations):
                matching_releases.append(release)
        
        return matching_releases

    def _tags_match(
        self, 
        release_tag: str, 
        image_tag: str, 
        match_type: str, 
        transformations: List[Dict[str, Any]]
    ) -> bool:
        """
        检查两个标签是否匹配
        
        Args:
            release_tag (str): 代码发布标签
            image_tag (str): 镜像标签
            match_type (str): 匹配类型
            transformations (List[Dict[str, Any]]): 标签转换规则
            
        Returns:
            bool: 是否匹配
        """
        # 应用标签转换规则
        transformed_release_tag = self._transform_tag(release_tag, transformations)
        transformed_image_tag = self._transform_tag(image_tag, transformations)
        
        if match_type == 'exact':
            return transformed_release_tag == transformed_image_tag
        elif match_type == 'prefix':
            return transformed_image_tag.startswith(transformed_release_tag) or \
                   transformed_release_tag.startswith(transformed_image_tag)
        elif match_type == 'regex':
            try:
                return bool(re.match(transformed_release_tag, transformed_image_tag)) or \
                       bool(re.match(transformed_image_tag, transformed_release_tag))
            except re.error:
                logger.warning(f"Invalid regex pattern: {transformed_release_tag} or {transformed_image_tag}")
                return False
        else:
            logger.warning(f"Unknown match type: {match_type}, using exact match")
            return transformed_release_tag == transformed_image_tag

    def _transform_tag(self, tag: str, transformations: List[Dict[str, Any]]) -> str:
        """
        应用标签转换规则
        
        Args:
            tag (str): 原始标签
            transformations (List[Dict[str, Any]]): 转换规则列表
            
        Returns:
            str: 转换后的标签
        """
        transformed_tag = tag
        
        for transformation in transformations:
            pattern = transformation.get('pattern', '')
            replacement = transformation.get('replacement', '')
            
            if not pattern:
                continue
            
            try:
                transformed_tag = re.sub(pattern, replacement, transformed_tag)
            except re.error as e:
                logger.warning(f"Invalid transformation pattern '{pattern}': {str(e)}")
                continue
        
        return transformed_tag

    def _create_relationship(self, image: Dict[str, Any], code_release: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建镜像来源于代码发布的关系数据
        
        Args:
            image (Dict[str, Any]): 镜像数据
            code_release (Dict[str, Any]): 代码发布数据
            
        Returns:
            Dict[str, Any]: 关系数据
        """
        try:
            # 生成实体ID（使用MD5哈希）
            image_entity_id = self._generate_entity_id(image, 'image')
            release_entity_id = self._generate_entity_id(code_release, 'code_release')
            
            # 构建关系数据
            relationship_data = {
                '__relation_type__': 'sourced_from',
                '__src_domain__': 'devops',
                '__src_entity_type__': 'devops.image',
                '__src_entity_id__': image_entity_id,
                '__dest_domain__': 'devops',
                '__dest_entity_type__': 'devops.code_release',
                '__dest_entity_id__': release_entity_id,
                
                # 关系属性
                'image_name': image.get('image_name', ''),
                'image_tag': image.get('tag', ''),
                'image_id': image.get('image_id', ''),
                'release_name': code_release.get('tag', ''),
                'release_id': code_release.get('release_id', ''),
                'repository_name': code_release.get('repo_name', ''),
                'priority': 5,  # 来自UModel定义
                'relationship_source': 'tag_mapping',
                'sourced_type': 'build_from_release'
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
                'code_release': ['release_id'],
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
        if not self.mapping_config:
            logger.error("Mapping config is not loaded")
            return False
        
        # 验证必要的配置部分
        required_sections = ['repo_image_mappings']
        for section in required_sections:
            if section not in self.mapping_config:
                logger.warning(f"Missing config section: {section}")
        
        repo_mappings = self.mapping_config.get('repo_image_mappings', {})
        logger.info(f"Config validation passed: {len(repo_mappings)} repository mappings loaded")
        return True

    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "image_sourced_from_code_release"
