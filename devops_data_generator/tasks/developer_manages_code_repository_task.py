import logging
import os
import yaml
from typing import Dict, List, Any

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class DeveloperManagesCodeRepositoryTask(BaseTask):
    """
    开发人员管理代码仓库关系生成任务
    
    基于管理配置文件中的映射关系，结合开发人员和代码仓库数据生成管理关系。
    依赖于 developer 和 code_repository 任务提供的数据。
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.task_type = 'relationship'  # 这是一个关系任务
        
        # 加载管理映射配置文件
        self.manage_config = self._load_manage_mapping()
        logger.info("Loaded management mapping configuration")
    
    def get_dependencies(self) -> List[str]:
        """
        声明依赖关系：依赖于 developer 和 code_repository 任务
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        return ["developer", "code_repository"]

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取开发人员管理代码仓库的关系数据
        
        基于管理配置文件中的映射关系，结合开发人员和代码仓库数据生成管理关系。
        如果配置文件中没有找到映射关系，则抛出错误。
        
        Returns:
            List[Dict[str, Any]]: 关系数据列表
            
        Raises:
            ValueError: 配置验证失败或找不到映射关系
            RuntimeError: 数据获取失败
        """
        if not self.validate_config():
            error_msg = "Configuration validation failed"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # 从共享上下文获取开发人员数据
            developers = self.get_shared_data("developer_list", [])
            if not developers:
                logger.warning("No developer data found in shared context")
                return []
            
            # 从共享上下文获取代码仓库数据
            repositories = self.get_shared_data("code_repository_raw_data", [])
            if not repositories:
                logger.warning("No repository data found in shared context")
                return []
            
            logger.info(f"Found {len(developers)} developers and {len(repositories)} repositories")
            logger.info(f"Using manage mapping config with {len(self.manage_config.get('manage_mappings', {}))} developer mappings")
            
            # 生成关系数据
            relationships = []
            missing_mappings = []
            
            # 创建开发人员和仓库的查找字典
            dev_name_to_data = {dev.get('name', ''): dev for dev in developers}
            repo_name_to_data = {repo.get('repo_name', ''): repo for repo in repositories}
            
            # 遍历管理配置文件中的映射关系
            manage_mappings = self.manage_config.get('manage_mappings', {})
            
            for dev_name, mapping_config in manage_mappings.items():
                # 查找对应的开发人员数据
                developer_data = dev_name_to_data.get(dev_name)
                if not developer_data:
                    logger.warning(f"Developer '{dev_name}' from config not found in developer data")
                    missing_mappings.append(f"Developer: {dev_name}")
                    continue
                
                dev_id = developer_data.get('dev_id') or developer_data.get('user_id')
                if not dev_id:
                    logger.warning(f"Developer '{dev_name}' missing dev_id")
                    continue
                
                # 处理该开发人员的仓库映射（简化版）
                repositories_list = mapping_config.get('repositories', [])
                
                for repo_name in repositories_list:
                    # 查找对应的仓库数据
                    repository_data = repo_name_to_data.get(repo_name)
                    if not repository_data:
                        logger.warning(f"Repository '{repo_name}' for developer '{dev_name}' not found in repository data")
                        missing_mappings.append(f"Repository: {repo_name} (for {dev_name})")
                        continue
                    
                    repo_id = repository_data.get('repo_id')
                    if not repo_id:
                        logger.warning(f"Repository '{repo_name}' missing repo_id")
                        continue
                    
                    # 生成简化的关系数据
                    relationship = {
                        'dev_id': dev_id,
                        'dev_name': dev_name,
                        'repo_id': repo_id,
                        'repo_name': repo_name,
                        'relationship_source': 'manage_mapping_config'
                    }
                    
                    relationships.append(relationship)
                    logger.debug(f"Created relationship: {dev_name} manages {repo_name}")
            
            # 检查是否有缺失的映射关系
            if missing_mappings:
                logger.warning("Missing mappings found: %s", ', '.join(missing_mappings))
            
            if not relationships:
                logger.info("No valid developer-repository relationships generated from manage mapping config")
                return []
            
            # 将关系数据存储到共享上下文
            self.set_shared_data("developer_manages_code_repository_list", relationships, "relationship_data")
            logger.info(f"Stored {len(relationships)} developer-repository relationships to shared context")
            
            logger.info(f"Successfully generated {len(relationships)} developer-repository relationships from config")
            return relationships
            
        except Exception as e:
            error_msg = f"Error generating developer-repository relationships: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _load_manage_mapping(self) -> Dict[str, Any]:
        """
        加载管理映射配置文件
        
        Returns:
            Dict[str, Any]: 管理映射配置数据
            
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
            config_path = os.path.join(config_dir, 'manage_mapping.yaml')
            
            if not os.path.exists(config_path):
                logger.warning(f"Manage mapping config file not found: {config_path}, using empty config")
                return {'manage_mappings': {}}
            
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            if not config or 'manage_mappings' not in config:
                logger.warning("Manage mapping config is empty or missing 'manage_mappings', using empty config")
                return {'manage_mappings': {}}
            
            # 验证配置格式
            manage_mappings = config.get('manage_mappings', {})
            for dev_name, dev_config in manage_mappings.items():
                if not isinstance(dev_config.get('repositories', []), list):
                    raise ValueError(f"Invalid config format for developer '{dev_name}': repositories must be a list")
                
                repositories = dev_config.get('repositories', [])
                for repo in repositories:
                    if not isinstance(repo, str):
                        raise ValueError(f"Invalid repository format for developer '{dev_name}': repository names must be strings")
            
            logger.info(f"Loaded manage mapping config from: {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading manage mapping config: {str(e)}")
            return {'manage_mappings': {}}

    def _validate_config_format(self) -> bool:
        """
        验证配置文件格式的有效性
        
        Returns:
            bool: 配置格式是否有效
        """
        try:
            manage_mappings = self.manage_config.get('manage_mappings', {})
            
            for dev_name, dev_config in manage_mappings.items():
                if not isinstance(dev_name, str) or not dev_name.strip():
                    logger.error(f"Invalid developer name: {dev_name}")
                    return False
                
                if not isinstance(dev_config, dict):
                    logger.error(f"Invalid config format for developer '{dev_name}': expected dict")
                    return False
                
                repositories = dev_config.get('repositories', [])
                if not isinstance(repositories, list):
                    logger.error(f"Invalid repositories format for developer '{dev_name}': expected list")
                    return False
                
                for repo in repositories:
                    if not isinstance(repo, str) or not repo.strip():
                        logger.error(f"Invalid repository name for developer '{dev_name}': {repo}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating config format: {str(e)}")
            return False

    def _find_repository_by_id(self, repositories: List[Dict[str, Any]], repo_id: str) -> Dict[str, Any]:
        """
        根据仓库ID查找仓库数据
        
        Args:
            repositories (List[Dict[str, Any]]): 仓库数据列表
            repo_id (str): 仓库ID
            
        Returns:
            Dict[str, Any]: 仓库数据，如果未找到返回None
        """
        for repo in repositories:
            if repo.get('repo_id') == repo_id:
                return repo
        return None

    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 配置是否有效
        """
        # 验证管理映射配置是否有效
        if not self.manage_config:
            logger.error("Manage mapping config is not loaded")
            return False
            
        manage_mappings = self.manage_config.get('manage_mappings', {})
        if not manage_mappings:
            logger.info("No manage mappings found in config, relationship generation will be skipped")
            return True
        
        # 验证配置格式
        if not self._validate_config_format():
            logger.error("Invalid config format")
            return False
            
        logger.info(f"Config validation passed: {len(manage_mappings)} developer mappings loaded")
        return True
