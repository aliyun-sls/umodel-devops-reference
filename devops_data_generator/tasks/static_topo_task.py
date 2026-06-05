#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静态Topo任务

从配置文件读取静态拓扑关系定义，生成拓扑数据
支持多种静态Topo关系类型的定义和生成
"""

import os
import yaml
import logging
from typing import List, Dict, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class StaticTopoTask(BaseTask):
    """
    静态Topo任务，用于生成基于配置文件定义的拓扑关系数据
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化静态Topo任务
        
        Args:
            config (Dict[str, Any]): 配置信息
        """
        super().__init__(config)
        self.task_type = 'relationship'  # 关系任务
        self.static_topo_config_path = config.get('static_topo_config', 'config/static_topo.yaml')
        self.static_topo_config = None
        
        # 加载静态Topo配置
        self._load_static_topo_config()
        
        logger.info(f"StaticTopoTask initialized with config: {self.static_topo_config_path}")
    
    def _load_static_topo_config(self):
        """
        加载静态Topo配置文件
        """
        try:
            config_path = self.static_topo_config_path
            if not os.path.isabs(config_path):
                # 相对路径，基于当前工作目录
                config_path = os.path.join(os.getcwd(), config_path)
            
            if not os.path.exists(config_path):
                logger.warning(f"Static topo config file not found: {config_path}")
                self.static_topo_config = {'topo_definitions': []}
                return
            
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or 'topo_definitions' not in config:
                raise ValueError("Invalid static topo config: missing 'topo_definitions' section")
            
            self.static_topo_config = config
            topo_count = len(config.get('topo_definitions', []))
            logger.info(f"Loaded static topo config with {topo_count} definitions from: {config_path}")
            
        except Exception as e:
            logger.error(f"Error loading static topo config: {str(e)}")
            raise
    
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        生成静态拓扑关系数据
        
        Returns:
            List[Dict[str, Any]]: 拓扑关系列表
            
        Raises:
            ValueError: 配置验证失败
            RuntimeError: 数据生成失败
        """
        if not self.validate_config():
            error_msg = "Configuration validation failed"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            topo_definitions = self.static_topo_config.get('topo_definitions', [])
            if not topo_definitions:
                logger.info("No topo definitions found in config")
                return []
            
            logger.info(f"Processing {len(topo_definitions)} topo definitions...")
            
            all_relationships = []
            
            # 处理每个Topo定义
            for i, topo_def in enumerate(topo_definitions):
                logger.info(f"Processing topo definition {i+1}: {topo_def.get('name', 'unnamed')}")
                
                relationships = self._process_topo_definition(topo_def)
                logger.info(f"Processed topo definition {i+1}: {topo_def.get('name', 'unnamed')}, generated {len(relationships)} relationships")
                all_relationships.extend(relationships)
            
            logger.info(f"Successfully generated {len(all_relationships)} static topo relationships")
            return all_relationships
            
        except Exception as e:
            error_msg = f"Error generating static topo data: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _process_topo_definition(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理单个Topo定义
        
        Args:
            topo_def (Dict[str, Any]): Topo定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        try:
            topo_type = topo_def.get('type', 'static')
            topo_name = topo_def.get('name', 'unnamed')
            
            logger.debug(f"Processing topo '{topo_name}' of type '{topo_type}'")
            
            if topo_type == 'static':
                return self._process_static_relationships(topo_def)
            elif topo_type == 'dynamic':
                return self._process_dynamic_relationships(topo_def)
            elif topo_type == 'cross_reference':
                return self._process_cross_reference_relationships(topo_def)
            elif topo_type == 'mixed':
                return self._process_mixed_relationships(topo_def)
            elif topo_type == 'dynamic_to_dynamic':
                return self._process_dynamic_to_dynamic_relationships(topo_def)
            else:
                logger.warning(f"Unknown topo type: {topo_type}")
                return []
                
        except Exception as e:
            logger.error(f"Error processing topo definition '{topo_def.get('name', 'unnamed')}': {str(e)}")
            return []
    
    def _process_static_relationships(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理静态关系定义
        
        Args:
            topo_def (Dict[str, Any]): 静态关系定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        static_relations = topo_def.get('relations', [])
        
        for relation in static_relations:
            # 对于静态关系，实体ID直接从配置中获取（已经是预定义的MD5值）
            relationship_data = {
                '__relation_type__': topo_def.get('relationship_type', 'static_link'),
                '__src_domain__': relation.get('source_domain', ''),
                '__src_entity_type__': relation.get('source_entity_type', ''),
                '__src_entity_id__': relation.get('source_entity_id', ''),
                '__dest_domain__': relation.get('target_domain', ''),
                '__dest_entity_type__': relation.get('target_entity_type', ''),
                '__dest_entity_id__': relation.get('target_entity_id', ''),
            }
            
            # 添加额外属性
            extra_attributes = relation.get('attributes', {})
            relationship_data.update(extra_attributes)
            
            relationships.append(relationship_data)
        
        logger.debug(f"Generated {len(relationships)} static relationships")
        return relationships
    
    def _process_dynamic_relationships(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理动态关系定义（基于共享数据）
        
        Args:
            topo_def (Dict[str, Any]): 动态关系定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        
        # 获取源实体数据
        source_entity_type = topo_def.get('source_entity_type', '')
        target_entity_type = topo_def.get('target_entity_type', '')
        
        source_data_key = f"{source_entity_type}_raw_data"
        target_data_key = f"{target_entity_type}_raw_data"
        
        source_data = self.get_shared_data(source_data_key, [])
        target_data = self.get_shared_data(target_data_key, [])
        
        if not source_data or not target_data:
            logger.warning(f"No data found for dynamic relationship: {source_data_key} or {target_data_key}")
            return relationships
        
        # 根据匹配规则生成关系
        match_rule = topo_def.get('match_rule', {})
        relationships = self._generate_dynamic_relationships(
            source_data, target_data, topo_def, match_rule
        )
        
        logger.debug(f"Generated {len(relationships)} dynamic relationships")
        return relationships
    
    def _process_cross_reference_relationships(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理交叉引用关系定义（多对多关系）
        
        Args:
            topo_def (Dict[str, Any]): 交叉引用关系定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        
        # 获取交叉引用配置
        cross_refs = topo_def.get('cross_references', [])
        
        for cross_ref in cross_refs:
            source_entities = cross_ref.get('source_entities', [])
            target_entities = cross_ref.get('target_entities', [])
            
            # 生成交叉关系
            for source in source_entities:
                for target in target_entities:
                    # 对于交叉引用关系，直接使用配置中的ID（已经是预定义的值）
                    relationship_data = {
                        '__relation_type__': topo_def.get('relationship_type', 'cross_reference'),
                        '__src_domain__': topo_def.get('source_domain', ''),
                        '__src_entity_type__': source.get('type', ''),
                        '__src_entity_id__': source.get('id', ''),
                        '__dest_domain__': topo_def.get('target_domain', ''),
                        '__dest_entity_type__': target.get('type', ''),
                        '__dest_entity_id__': target.get('id', ''),
                        '__keep_alive_seconds__': '600',
                        'relationship_name': topo_def.get('name', 'cross_reference'),
                        'relationship_source': 'cross_reference_config'
                    }
                    
                    # 添加额外属性
                    extra_attributes = cross_ref.get('attributes', {})
                    relationship_data.update(extra_attributes)
                    
                    relationships.append(relationship_data)
        
        logger.debug(f"Generated {len(relationships)} cross-reference relationships")
        return relationships
    
    def _process_mixed_relationships(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理混合关系定义（静态实体与动态实体的关系）
        
        Args:
            topo_def (Dict[str, Any]): 混合关系定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        
        try:
            # 获取静态实体定义
            static_entities = topo_def.get('static_entities', [])
            if not static_entities:
                logger.warning(f"No static entities found in mixed relationship: {topo_def.get('name')}")
                return relationships
            
            # 获取动态实体配置
            dynamic_entity_config = topo_def.get('dynamic_entity', {})
            if not dynamic_entity_config:
                logger.warning(f"No dynamic entity config found in mixed relationship: {topo_def.get('name')}")
                return relationships
            
            # 获取动态实体数据
            dynamic_entity_type = dynamic_entity_config.get('entity_type', '')
            
            # 定义动态数据键名映射
            dynamic_data_key_mapping = {
                'devops.code_release': 'code_release_list',
                'devops.developer': 'devops.developer_raw_data',
                'devops.code_repository': 'code_repos'
            }
            
            dynamic_data_key = dynamic_data_key_mapping.get(dynamic_entity_type, f"{dynamic_entity_type}_raw_data")
            dynamic_data = self.get_shared_data(dynamic_data_key, [])
            
            if not dynamic_data:
                logger.warning(f"No dynamic data found for entity type: {dynamic_entity_type}")
                return relationships
            
            # 获取匹配规则
            match_rule = topo_def.get('match_rule', {})
            
            logger.info(f"Processing mixed relationship: {len(static_entities)} static entities, {len(dynamic_data)} dynamic entities")
            
            # 为每个静态实体寻找匹配的动态实体
            for static_entity in static_entities:
                matching_dynamic_entities = self._find_matching_dynamic_entities(
                    static_entity, dynamic_data, match_rule
                )
                
                # 生成关系
                for dynamic_entity in matching_dynamic_entities:
                    relationship_data = self._create_mixed_relationship(
                        static_entity, dynamic_entity, topo_def, match_rule
                    )
                    if relationship_data:
                        relationships.append(relationship_data)
            
            logger.debug(f"Generated {len(relationships)} mixed relationships")
            return relationships
            
        except Exception as e:
            logger.error(f"Error processing mixed relationships: {str(e)}")
            return relationships
    
    def _process_dynamic_to_dynamic_relationships(self, topo_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理动态到动态关系定义（动态实体与动态实体的关系）
        
        Args:
            topo_def (Dict[str, Any]): 动态到动态关系定义
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        
        try:
            topo_name = topo_def.get('name', 'unnamed')
            logger.info(f"Processing dynamic-to-dynamic relationship: {topo_name}")
            
            # 获取源动态实体配置
            source_entity_config = topo_def.get('source_entity', {})
            target_entity_config = topo_def.get('target_entity', {})
            
            if not source_entity_config or not target_entity_config:
                logger.warning(f"Missing source or target entity config in dynamic-to-dynamic relationship: {topo_name}")
                return relationships
            
            # 获取源动态实体数据
            source_data_key = source_entity_config.get('data_key', '')
            source_entity_type = source_entity_config.get('entity_type', '')
            source_id_field = source_entity_config.get('id_field', 'id')
            
            source_data = self.get_shared_data(source_data_key, [])
            if not source_data:
                logger.warning(f"No source data found for key '{source_data_key}' in dynamic-to-dynamic relationship: {topo_name}")
                return relationships
            
            # 获取目标动态实体数据
            target_data_key = target_entity_config.get('data_key', '')
            target_entity_type = target_entity_config.get('entity_type', '')
            target_id_field = target_entity_config.get('id_field', 'id')
            
            target_data = self.get_shared_data(target_data_key, [])
            if not target_data:
                logger.warning(f"No target data found for key '{target_data_key}' in dynamic-to-dynamic relationship: {topo_name}")
                return relationships
            
            # 获取关系映射配置
            relationship_mapping = topo_def.get('relationship_mapping', [])
            if not relationship_mapping:
                logger.warning(f"No relationship mapping found in dynamic-to-dynamic relationship: {topo_name}")
                return relationships
            
            logger.info(f"Processing dynamic-to-dynamic: {len(source_data)} source entities, {len(target_data)} target entities, {len(relationship_mapping)} mappings")
            
            # 处理每个关系映射
            for mapping in relationship_mapping:
                source_filter = mapping.get('source_filter', {})
                target_filter = mapping.get('target_filter', {})
                mapping_attributes = mapping.get('attributes', {})
                
                # 查找匹配的源实体
                matching_source_entities = self._find_entities_by_filter(source_data, source_filter)
                # 查找匹配的目标实体
                matching_target_entities = self._find_entities_by_filter(target_data, target_filter)
                
                # 生成关系
                for source_entity in matching_source_entities:
                    for target_entity in matching_target_entities:
                        relationship_data = self._create_dynamic_to_dynamic_relationship(
                            source_entity, target_entity, topo_def, mapping_attributes,
                            source_entity_type, target_entity_type, source_id_field, target_id_field
                        )
                        if relationship_data:
                            relationships.append(relationship_data)
            
            logger.info(f"Generated {len(relationships)} dynamic-to-dynamic relationships for {topo_name}")
            return relationships
            
        except Exception as e:
            logger.error(f"Error processing dynamic-to-dynamic relationships: {str(e)}")
            return relationships
    
    def _find_matching_dynamic_entities(
        self, 
        static_entity: Dict[str, Any], 
        dynamic_data: List[Dict[str, Any]], 
        match_rule: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        寻找与静态实体匹配的动态实体
        
        Args:
            static_entity: 静态实体数据
            dynamic_data: 动态实体数据列表
            match_rule: 匹配规则
            
        Returns:
            List[Dict[str, Any]]: 匹配的动态实体列表
        """
        matching_entities = []
        
        try:
            static_match_field = match_rule.get('static_field', 'id')
            dynamic_match_field = match_rule.get('dynamic_field', 'id')
            match_type = match_rule.get('type', 'exact')
            
            # 获取静态实体的匹配值
            static_value = static_entity.get(static_match_field, '')
            if not static_value:
                logger.warning(f"Static entity missing match field '{static_match_field}': {static_entity}")
                return matching_entities
            
            # 查找匹配的动态实体
            for dynamic_entity in dynamic_data:
                dynamic_value = dynamic_entity.get(dynamic_match_field, '')
                if not dynamic_value:
                    continue
                
                if self._check_match(static_value, dynamic_value, match_type):
                    matching_entities.append(dynamic_entity)
                    logger.debug(f"Found match: static '{static_value}' -> dynamic '{dynamic_value}'")
            
        except Exception as e:
            logger.error(f"Error finding matching entities: {str(e)}")
        
        return matching_entities
    
    def _create_mixed_relationship(
        self, 
        static_entity: Dict[str, Any], 
        dynamic_entity: Dict[str, Any], 
        topo_def: Dict[str, Any],
        match_rule: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建混合关系数据
        
        Args:
            static_entity: 静态实体数据
            dynamic_entity: 动态实体数据
            topo_def: Topo定义
            match_rule: 匹配规则
            
        Returns:
            Dict[str, Any]: 关系数据
        """
        try:
            # 确定关系方向
            relation_direction = topo_def.get('relation_direction', 'static_to_dynamic')
            
            if relation_direction == 'static_to_dynamic':
                # 静态实体作为源，动态实体作为目标
                source_entity = static_entity
                target_entity = dynamic_entity
                source_entity_type = topo_def.get('static_entity_type', '')
                target_entity_type = topo_def.get('dynamic_entity', {}).get('entity_type', '')
            else:
                # 动态实体作为源，静态实体作为目标
                source_entity = dynamic_entity
                target_entity = static_entity
                source_entity_type = topo_def.get('dynamic_entity', {}).get('entity_type', '')
                target_entity_type = topo_def.get('static_entity_type', '')
            
            # 获取实体ID：静态实体使用预定义值，动态实体计算生成
            if relation_direction == 'static_to_dynamic':
                # 静态实体作为源：直接使用配置中的entity_id
                source_entity_id = source_entity.get('entity_id', '')
                # 动态实体作为目标：使用计算生成
                target_entity_id = self._generate_entity_id(target_entity, target_entity_type)
            else:
                # 动态实体作为源：使用计算生成
                source_entity_id = self._generate_entity_id(source_entity, source_entity_type)
                # 静态实体作为目标：直接使用配置中的entity_id
                target_entity_id = target_entity.get('entity_id', '')
            
            # 构建关系数据
            relationship_data = {
                '__relation_type__': topo_def.get('relationship_type', 'mixed_link'),
                '__src_domain__': source_entity.get('domain', topo_def.get('source_domain', '')),
                '__src_entity_type__': source_entity_type,
                '__src_entity_id__': source_entity_id,
                '__dest_domain__': target_entity.get('domain', topo_def.get('target_domain', '')),
                '__dest_entity_type__': target_entity_type,
                '__dest_entity_id__': target_entity_id,
                '__keep_alive_seconds__': '600',
            }
            
            # 添加额外属性
            extra_attributes = topo_def.get('attributes', {})
            relationship_data.update(extra_attributes)
            
            return relationship_data
            
        except Exception as e:
            logger.error(f"Error creating mixed relationship: {str(e)}")
            return {}
    
    def _generate_entity_id(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        根据实体类型和数据生成实体ID，与data_mapping.yaml中的__entity_id__生成规则保持一致
        
        Args:
            entity: 实体数据
            entity_type: 实体类型
            
        Returns:
            str: 实体ID（MD5哈希值）
        """
        import hashlib
        
        try:
            # 根据实体类型获取主键字段
            entity_primary_keys = self._get_entity_primary_keys(entity_type)
            
            if not entity_primary_keys:
                logger.warning(f"No primary keys found for entity type: {entity_type}")
                # 使用备用ID字段
                fallback_id = entity.get('entity_id', entity.get('id', ''))
                return str(fallback_id) if fallback_id else ''
            
            # 获取主键值并组合
            primary_key_values = []
            for key in entity_primary_keys:
                value = entity.get(key, '')
                if not value:
                    logger.debug(f"Primary key '{key}' not found in entity data for type '{entity_type}'")
                primary_key_values.append(str(value))
            
            # 生成实体ID（基于主键字段的MD5哈希）
            primary_key_string = '|'.join(primary_key_values)
            if primary_key_string:
                entity_id = hashlib.md5(primary_key_string.encode('utf-8')).hexdigest()
            else:
                # 如果主键为空，使用备用ID
                entity_id = str(entity.get('entity_id', entity.get('id', '')))
            
            logger.debug(f"Generated entity ID '{entity_id}' for type '{entity_type}' using keys {entity_primary_keys}")
            return entity_id
            
        except Exception as e:
            logger.error(f"Error generating entity ID for type '{entity_type}': {str(e)}")
            return str(entity.get('entity_id', entity.get('id', '')))
    
    def _get_entity_primary_keys(self, entity_type: str) -> List[str]:
        """
        根据实体类型获取主键字段列表
        
        Args:
            entity_type: 实体类型
            
        Returns:
            List[str]: 主键字段列表
        """
        # 从data_mapping.yaml中获取的主键配置
        entity_primary_keys_mapping = {
            'devops.code_repository': ['repo_id'],
            'devops.code_release': ['release_id'],
            'devops.developer': ['user_id'],  # 映射后的字段名
            'devops.image': ['image_id'],
            'devops.image_registry': ['registry_id'],
            'apm.service': ['entity_id'],  # 静态实体使用entity_id
        }
        
        # 获取对应的主键字段
        primary_keys = entity_primary_keys_mapping.get(entity_type, [])
        
        # 如果找不到配置，尝试常见的主键字段
        if not primary_keys:
            common_id_fields = ['id', 'entity_id', 'release_id', 'repo_id', 'user_id', 'image_id', 'registry_id']
            primary_keys = [field for field in common_id_fields if field in ['id']]  # 默认使用id
        
        return primary_keys
    
    def _generate_dynamic_relationships(
        self, 
        source_data: List[Dict[str, Any]], 
        target_data: List[Dict[str, Any]], 
        topo_def: Dict[str, Any], 
        match_rule: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        基于匹配规则生成动态关系
        
        Args:
            source_data: 源实体数据
            target_data: 目标实体数据
            topo_def: Topo定义
            match_rule: 匹配规则
            
        Returns:
            List[Dict[str, Any]]: 关系数据列表
        """
        relationships = []
        
        source_field = match_rule.get('source_field', 'id')
        target_field = match_rule.get('target_field', 'id')
        match_type = match_rule.get('type', 'exact')  # exact, contains, regex
        
        for source_item in source_data:
            source_value = source_item.get(source_field, '')
            if not source_value:
                continue
                
            for target_item in target_data:
                target_value = target_item.get(target_field, '')
                if not target_value:
                    continue
                
                # 检查匹配条件
                if self._check_match(source_value, target_value, match_type):
                    # 生成实体ID（与data_mapping.yaml保持一致）
                    source_entity_id = self._generate_entity_id(source_item, topo_def.get('source_entity_type', ''))
                    target_entity_id = self._generate_entity_id(target_item, topo_def.get('target_entity_type', ''))
                    
                    relationship_data = {
                        '__relation_type__': topo_def.get('relationship_type', 'dynamic_link'),
                        '__src_domain__': topo_def.get('source_domain', ''),
                        '__src_entity_type__': topo_def.get('source_entity_type', ''),
                        '__src_entity_id__': source_entity_id,
                        '__dest_domain__': topo_def.get('target_domain', ''),
                        '__dest_entity_type__': topo_def.get('target_entity_type', ''),
                        '__dest_entity_id__': target_entity_id,
                        '__keep_alive_seconds__': '600',
                        'relationship_name': topo_def.get('name', 'dynamic_relationship'),
                        'relationship_source': 'dynamic_config',
                        'match_field_source': source_field,
                        'match_field_target': target_field,
                        'match_value_source': str(source_value),
                        'match_value_target': str(target_value)
                    }
                    
                    relationships.append(relationship_data)
        
        return relationships
    
    def _check_match(self, source_value: Any, target_value: Any, match_type: str) -> bool:
        """
        检查两个值是否匹配
        
        Args:
            source_value: 源值
            target_value: 目标值
            match_type: 匹配类型
            
        Returns:
            bool: 是否匹配
        """
        source_str = str(source_value)
        target_str = str(target_value)
        
        if match_type == 'exact':
            return source_str == target_str
        elif match_type == 'contains':
            return source_str in target_str or target_str in source_str
        elif match_type == 'regex':
            import re
            try:
                return bool(re.search(source_str, target_str))
            except re.error:
                logger.warning(f"Invalid regex pattern: {source_str}")
                return False
        else:
            return source_str == target_str
    
    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 配置是否有效
        """
        if not self.static_topo_config:
            logger.error("Static topo config is not loaded")
            return False
        
        topo_definitions = self.static_topo_config.get('topo_definitions', [])
        if not topo_definitions:
            logger.warning("No topo definitions found in config")
            return True  # 空配置也是有效的
        
        # 验证每个定义的基本结构
        for i, topo_def in enumerate(topo_definitions):
            if not isinstance(topo_def, dict):
                logger.error(f"Topo definition {i} is not a dictionary")
                return False
            
            if 'type' not in topo_def:
                logger.error(f"Topo definition {i} missing 'type' field")
                return False
        
        logger.info(f"Config validation passed: {len(topo_definitions)} topo definitions loaded")
        return True
    
    def _find_entities_by_filter(self, entities: List[Dict[str, Any]], filter_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        根据过滤条件查找匹配的实体
        
        Args:
            entities (List[Dict[str, Any]]): 实体数据列表
            filter_config (Dict[str, Any]): 过滤条件
            
        Returns:
            List[Dict[str, Any]]: 匹配的实体列表
        """
        matching_entities = []
        
        try:
            if not filter_config:
                return entities  # 没有过滤条件，返回所有实体
            
            for entity in entities:
                is_match = True
                
                # 检查所有过滤条件
                for field_name, expected_value in filter_config.items():
                    entity_value = entity.get(field_name, None)
                    
                    # 支持字符串匹配
                    if str(entity_value) != str(expected_value):
                        is_match = False
                        break
                
                if is_match:
                    matching_entities.append(entity)
            
            logger.debug(f"Filter {filter_config} matched {len(matching_entities)} entities out of {len(entities)}")
            return matching_entities
            
        except Exception as e:
            logger.error(f"Error filtering entities: {str(e)}")
            return []
    
    def _create_dynamic_to_dynamic_relationship(
        self, 
        source_entity: Dict[str, Any], 
        target_entity: Dict[str, Any], 
        topo_def: Dict[str, Any],
        mapping_attributes: Dict[str, Any],
        source_entity_type: str,
        target_entity_type: str,
        source_id_field: str,
        target_id_field: str
    ) -> Dict[str, Any]:
        """
        创建动态到动态关系数据
        
        Args:
            source_entity: 源实体数据
            target_entity: 目标实体数据
            topo_def: 关系定义
            mapping_attributes: 映射特定的属性
            source_entity_type: 源实体类型
            target_entity_type: 目标实体类型
            source_id_field: 源实体ID字段名
            target_id_field: 目标实体ID字段名
            
        Returns:
            Dict[str, Any]: 关系数据
        """
        try:
            # 生成实体ID
            source_entity_id = self._generate_entity_id(source_entity, source_entity_type)
            target_entity_id = self._generate_entity_id(target_entity, target_entity_type)
            
            # 构建关系数据
            relationship_data = {
                '__relation_type__': topo_def.get('relationship_type', 'manages'),
                '__src_domain__': topo_def.get('source_domain', 'devops'),
                '__src_entity_type__': f"{source_entity_type}",
                '__src_entity_id__': source_entity_id,
                '__dest_domain__': topo_def.get('target_domain', 'devops'),
                '__dest_entity_type__': f"{target_entity_type}",
                '__dest_entity_id__': target_entity_id,
                '__keep_alive_seconds__': '600',
            }
            
            # 添加通用关系属性
            general_attributes = topo_def.get('attributes', {})
            relationship_data.update(general_attributes)
            
            # 添加映射特定的属性
            relationship_data.update(mapping_attributes)
            
            # 添加实体相关信息
            relationship_data.update({
                'source_entity_info': {
                    'id': source_entity.get(source_id_field, ''),
                    'name': source_entity.get('name', source_entity.get('user_name', ''))
                },
                'target_entity_info': {
                    'id': target_entity.get(target_id_field, ''),
                    'name': target_entity.get('name', target_entity.get('repo_name', ''))
                }
            })
            
            logger.debug(f"Created dynamic-to-dynamic relationship: {source_entity_type}({source_entity.get(source_id_field)}) -> {target_entity_type}({target_entity.get(target_id_field)})")
            return relationship_data
            
        except Exception as e:
            logger.error(f"Error creating dynamic-to-dynamic relationship: {str(e)}")
            return {}
    
    def get_dependencies(self) -> List[str]:
        """
        获取task依赖列表
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        dependencies = []
        
        if self.static_topo_config:
            # 从配置中提取依赖的实体类型
            topo_definitions = self.static_topo_config.get('topo_definitions', [])
            entity_types = set()
            
            for topo_def in topo_definitions:
                if topo_def.get('type') == 'dynamic':
                    source_type = topo_def.get('source_entity_type', '')
                    target_type = topo_def.get('target_entity_type', '')
                    if source_type:
                        entity_types.add(source_type)
                    if target_type:
                        entity_types.add(target_type)
            
            dependencies = list(entity_types)
        
        logger.debug(f"Static topo dependencies: {dependencies}")
        return dependencies
    
    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "static_topo"
