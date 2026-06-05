import hashlib
import logging
import time
from typing import Dict, List, Any, Union
from datetime import datetime
import yaml

logger = logging.getLogger(__name__)


class SlsDataGenerator:
    """
    SLS数据生成器
    
    将Task获取的数据根据配置模板映射成阿里云简单日志服务（SLS）数据结构
    """
    
    def __init__(self, config_file: str):
        """
        初始化数据生成器
        
        Args:
            config_file (str): 配置文件路径
        """
        self.config = self._load_config(config_file)
        self.entities = self.config.get('entity', {})
        self.relationships = self.config.get('topo', {})
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_file (str): 配置文件路径
            
        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Successfully loaded config from {config_file}")
                return config
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {str(e)}")
            raise
    
    def generate_entity_data(self, entity_type: str, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成实体数据
        
        Args:
            entity_type (str): 实体类型
            raw_data (List[Dict[str, Any]]): 原始数据
            
        Returns:
            List[Dict[str, Any]]: SLS格式的实体数据
        """
        if entity_type not in self.entities:
            logger.error(f"Unknown entity type: {entity_type}")
            return []
        
        entity_config = self.entities[entity_type]
        sls_entities = []
        
        for data in raw_data:
            sls_entity = self._create_entity_item(entity_config, data)
            if sls_entity:
                sls_entities.append(sls_entity)
        
        logger.info(f"Generated {len(sls_entities)} {entity_type} entities")
        return sls_entities
    
    def _create_entity_item(self, entity_config: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建单个实体项目
        
        Args:
            entity_config (Dict[str, Any]): 实体配置
            data (Dict[str, Any]): 原始数据
            
        Returns:
            Dict[str, Any]: SLS格式的实体数据
        """
        try:
            # 提取配置信息
            fields = entity_config.get('fields', [])
            primary_keys = entity_config.get('primaryKeys', [])
            domain = entity_config.get('__domain__')
            entity_type = entity_config.get('__entity_type__')
            use_field_as_entity_id = entity_config.get('use_field_as_entity_id')
            
            # 创建基础实体结构
            entity_item = {
                '__domain__': domain,
                '__entity_type__': entity_type,
                '__time__': int(time.time())
            }
            
            # 解析字段配置，分离动态字段、映射字段和固定值字段
            dynamic_fields = []      # [(source_field, target_field), ...]
            fixed_fields = {}        # {target_field: value, ...}
            
            for field_config in fields:
                if isinstance(field_config, str):
                    # 检查是否为映射字段格式 "source -> target"
                    if ' -> ' in field_config:
                        # 映射字段：源字段名映射到目标字段名
                        parts = field_config.split(' -> ')
                        if len(parts) == 2:
                            source_field = parts[0].strip()
                            target_field = parts[1].strip()
                            dynamic_fields.append((source_field, target_field))
                        else:
                            logger.warning(f"Invalid field mapping format: {field_config}")
                            # 作为普通字段处理
                            dynamic_fields.append((field_config, field_config))
                    else:
                        # 动态字段：简单字符串格式（源字段名和目标字段名相同）
                        dynamic_fields.append((field_config, field_config))
                elif isinstance(field_config, dict):
                    # 固定值字段：键值对格式
                    for field_name, field_value in field_config.items():
                        fixed_fields[field_name] = field_value
            
            # 生成entity_id - 支持两种方式
            if use_field_as_entity_id:
                # 方式1：直接使用指定字段作为entity_id
                entity_id_value = ''
                # 查找指定字段的值
                if use_field_as_entity_id in fixed_fields:
                    entity_id_value = self._resolve_field_value(fixed_fields[use_field_as_entity_id])
                else:
                    # 从动态字段映射中查找
                    found = False
                    for source_field, target_field in dynamic_fields:
                        if target_field == use_field_as_entity_id and source_field in data:
                            entity_id_value = data[source_field]
                            found = True
                            break
                    if not found:
                        # 直接从数据中查找
                        entity_id_value = data.get(use_field_as_entity_id, '')
                
                if not entity_id_value:
                    logger.warning(f"Field '{use_field_as_entity_id}' specified for entity_id not found in data for entity {entity_type}")
                    entity_id_value = ''
                
                entity_item['__entity_id__'] = str(entity_id_value)
                logger.debug(f"Using field '{use_field_as_entity_id}' as entity_id: {entity_id_value}")
            else:
                # 方式2：使用主键MD5哈希生成entity_id（默认方式）
                primary_key_values = []
                for key in primary_keys:
                    # 首先从固定值字段获取
                    if key in fixed_fields:
                        value = self._resolve_field_value(fixed_fields[key])
                    else:
                        # 从动态字段映射中查找
                        found = False
                        for source_field, target_field in dynamic_fields:
                            if target_field == key and source_field in data:
                                value = data[source_field]
                                found = True
                                break
                        if not found:
                            # 直接从数据中查找
                            value = data.get(key, '')
                            if not value:
                                logger.warning(f"Primary key {key} not found in data or field mappings for entity {entity_type}")
                    primary_key_values.append(str(value))
                
                primary_key_string = '|'.join(primary_key_values)
                entity_id = hashlib.md5(primary_key_string.encode('utf-8')).hexdigest()
                entity_item['__entity_id__'] = entity_id
                logger.debug(f"Generated MD5 entity_id from primary keys {primary_keys}: {entity_id}")
            
            # 添加动态字段数据（支持字段映射）
            for source_field, target_field in dynamic_fields:
                if source_field in data:
                    entity_item[target_field] = data[source_field]
                else:
                    logger.warning(f"Source field '{source_field}' not found in data for entity {entity_type}, mapping to '{target_field}'")
                    entity_item[target_field] = ''
            
            # 添加固定值字段数据
            for field_name, field_value in fixed_fields.items():
                entity_item[field_name] = self._resolve_field_value(field_value)
            
            return entity_item
        
        except Exception as e:
            logger.error(f"Error creating entity item: {str(e)}")
            return {}
    
    def _resolve_field_value(self, value: Any) -> Any:
        """
        解析字段值，支持特殊值处理
        
        Args:
            value (Any): 配置中的字段值
            
        Returns:
            Any: 解析后的实际值
        """
        if isinstance(value, str):
            if value == "auto":
                # 特殊值：自动生成当前时间戳
                return datetime.now().isoformat()
            elif value.startswith("auto:"):
                # 扩展自动值：auto:timestamp, auto:uuid等
                auto_type = value[5:]  # 去掉 "auto:" 前缀
                if auto_type == "timestamp":
                    return int(time.time())
                elif auto_type == "datetime":
                    return datetime.now().isoformat()
                elif auto_type == "date":
                    return datetime.now().strftime("%Y-%m-%d")
                else:
                    logger.warning(f"Unknown auto type: {auto_type}")
                    return value
        
        return value
    
    def generate_relationship_data(self, relationship_type: str, 
                                   src_entities: List[Dict[str, Any]], 
                                   dest_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成关系数据
        
        Args:
            relationship_type (str): 关系类型
            src_entities (List[Dict[str, Any]]): 源实体列表
            dest_entities (List[Dict[str, Any]]): 目标实体列表
            
        Returns:
            List[Dict[str, Any]]: SLS格式的关系数据
        """
        if relationship_type not in self.relationships:
            logger.error(f"Unknown relationship type: {relationship_type}")
            return []
        
        relationship_config = self.relationships[relationship_type]
        sls_relationships = []
        
        # 创建实体映射以便快速查找
        src_entity_map = {}
        dest_entity_map = {}
        
        for entity in src_entities:
            entity_id = entity.get('__entity_id__')
            if entity_id:
                src_entity_map[entity_id] = entity
        
        for entity in dest_entities:
            entity_id = entity.get('__entity_id__')
            if entity_id:
                dest_entity_map[entity_id] = entity
        
        # 根据业务逻辑生成关系
        for src_entity in src_entities:
            for dest_entity in dest_entities:
                # 这里可以根据具体的业务逻辑来判断两个实体是否有关系
                # 示例：如果是开发人员和代码仓库的关系，可以根据团队匹配等
                relationship_item = self._create_relationship_item(
                    relationship_config, src_entity, dest_entity
                )
                if relationship_item:
                    sls_relationships.append(relationship_item)
        
        logger.info(f"Generated {len(sls_relationships)} {relationship_type} relationships")
        return sls_relationships
    
    def _create_relationship_item(self, relationship_config: Dict[str, Any], 
                                  src_entity: Dict[str, Any], 
                                  dest_entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建单个关系项目
        
        Args:
            relationship_config (Dict[str, Any]): 关系配置
            src_entity (Dict[str, Any]): 源实体
            dest_entity (Dict[str, Any]): 目标实体
            
        Returns:
            Dict[str, Any]: SLS格式的关系数据
        """
        try:
            relationship_item = {
                '__src_domain__': relationship_config.get('__src_domain__'),
                '__src_entity_type__': relationship_config.get('__src_entity_type__'),
                '__src_entity_id__': src_entity.get('__entity_id__'),
                '__dest_domain__': relationship_config.get('__dest_domain__'),
                '__dest_entity_type__': relationship_config.get('__dest_entity_type__'),
                '__dest_entity_id__': dest_entity.get('__entity_id__'),
                '__time__': int(time.time())
            }
            
            # 添加关系的固定值字段
            fixed_fields = relationship_config.get('fixed_fields', {})
            for field_name, field_value in fixed_fields.items():
                relationship_item[field_name] = self._resolve_field_value(field_value)
            
            return relationship_item
            
        except Exception as e:
            logger.error(f"Error creating relationship item: {str(e)}")
            return {}
    
    def get_supported_entities(self) -> List[str]:
        """
        获取支持的实体类型列表
        
        Returns:
            List[str]: 支持的实体类型
        """
        return list(self.entities.keys())
    
    def get_supported_relationships(self) -> List[str]:
        """
        获取支持的关系类型列表
        
        Returns:
            List[str]: 支持的关系类型
        """
        return list(self.relationships.keys())
