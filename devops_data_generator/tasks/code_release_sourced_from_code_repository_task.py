#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码发布-来源于-代码仓库关系任务

基于UModel定义自动生成 devops.code_release_sourced_from_devops.code_repository 关系
- 源实体：devops.code_release
- 目标实体：devops.code_repository  
- 关系类型：sourced_from
- 关联字段：repo_id
"""

import logging
from typing import List, Dict, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class CodeReleaseSourcedFromCodeRepositoryTask(BaseTask):
    """
    代码发布来源于代码仓库关系任务
    
    根据code_release和code_repository的repo_id关联字段，
    自动生成sourced_from关系数据
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化任务
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.task_type = 'relationship'  # 关系任务
        logger.info("CodeReleaseSourcedFromCodeRepositoryTask initialized")
    
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        生成code_release与code_repository之间的sourced_from关系
        
        Returns:
            List[Dict[str, Any]]: 关系数据列表
            
        Raises:
            RuntimeError: 数据获取失败
        """
        try:
            # 从共享数据获取code_release和code_repository数据
            code_release_data = self.get_shared_data("code_release_list", [])
            code_repository_data = self.get_shared_data("code_repos", [])
            
            if not code_release_data:
                logger.warning("No code_release data found in shared context")
                return []
            
            if not code_repository_data:
                logger.warning("No code_repository data found in shared context")
                return []
            
            logger.info(f"Processing relationships: {len(code_release_data)} releases, {len(code_repository_data)} repositories")
            
            # 构建repo_id到repository的映射
            repo_map = {}
            for repo in code_repository_data:
                repo_id = repo.get('repo_id', '')
                if repo_id:
                    repo_map[repo_id] = repo
            
            logger.debug(f"Built repository mapping for {len(repo_map)} repositories")
            
            # 生成关系数据
            relationships = []
            
            for release in code_release_data:
                release_repo_id = release.get('repo_id', '')
                if not release_repo_id:
                    logger.warning(f"Release missing repo_id: {release.get('release_id', 'unknown')}")
                    continue
                
                # 查找对应的repository
                if release_repo_id not in repo_map:
                    logger.warning(f"No repository found for repo_id: {release_repo_id}")
                    continue
                
                repository = repo_map[release_repo_id]
                
                # 构建关系数据
                relationship = self._create_relationship(release, repository)
                if relationship:
                    relationships.append(relationship)
            
            logger.info(f"Generated {len(relationships)} code_release_sourced_from_code_repository relationships")
            return relationships
            
        except Exception as e:
            error_msg = f"Error generating code_release_sourced_from_code_repository relationships: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _create_relationship(
        self, 
        release: Dict[str, Any], 
        repository: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建单个关系数据
        
        Args:
            release: code_release实体数据
            repository: code_repository实体数据
            
        Returns:
            Dict[str, Any]: 关系数据，如果创建失败返回空字典
        """
        try:
            # 获取实体ID（使用与data_mapping.yaml一致的生成规则）
            release_id = self._generate_entity_id(release, 'code_release')
            repository_id = self._generate_entity_id(repository, 'code_repository')
            
            if not release_id or not repository_id:
                logger.warning(f"Failed to generate entity IDs: release_id={release_id}, repository_id={repository_id}")
                return {}
            
            # 构建关系数据（遵循UModel定义）
            relationship = {
                '__relation_type__': 'sourced_from',
                '__src_domain__': 'devops',
                '__src_entity_type__': 'devops.code_release',
                '__src_entity_id__': release_id,
                '__dest_domain__': 'devops',
                '__dest_entity_type__': 'devops.code_repository', 
                '__dest_entity_id__': repository_id,
                
                # 关系属性
                'release_name': release.get('tag', ''),
                'repository_name': repository.get('repo_name', ''),
            }
            
            logger.debug(f"Created relationship: {release.get('tag', '')} sourced_from {repository.get('repo_name', '')}")
            return relationship
            
        except Exception as e:
            logger.error(f"Error creating relationship: {str(e)}")
            return {}
    
    def _generate_entity_id(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        生成实体ID（与data_mapping.yaml保持一致）
        
        Args:
            entity: 实体数据
            entity_type: 实体类型
            
        Returns:
            str: 实体ID（MD5哈希值）
        """
        import hashlib
        
        try:
            # 根据实体类型获取主键字段
            primary_key_mapping = {
                'code_release': ['release_id'],
                'code_repository': ['repo_id']
            }
            
            primary_keys = primary_key_mapping.get(entity_type, ['id'])
            
            # 获取主键值并组合
            primary_key_values = []
            for key in primary_keys:
                value = entity.get(key, '')
                primary_key_values.append(str(value))
            
            # 生成MD5哈希
            primary_key_string = '|'.join(primary_key_values)
            if primary_key_string:
                entity_id = hashlib.md5(primary_key_string.encode('utf-8')).hexdigest()
                return entity_id
            else:
                logger.warning(f"Empty primary key string for entity type: {entity_type}")
                return ''
                
        except Exception as e:
            logger.error(f"Error generating entity ID for type '{entity_type}': {str(e)}")
            return ''
    
    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 配置是否有效
        """
        # 这个任务不需要额外配置，始终有效
        return True
    
    def get_dependencies(self) -> List[str]:
        """
        获取task依赖列表
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        # 依赖于code_release和code_repository任务
        return ['code_release', 'code_repository']
    
    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "code_release_sourced_from_code_repository"
