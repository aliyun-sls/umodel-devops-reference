from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseTask(ABC):
    """
    基础任务抽象类，定义任务接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.access_key_id = config.get('access_key_id')
        self.access_key_secret = config.get('access_key_secret')
        self.region = config.get('region', 'cn-hangzhou')
        self.shared_context = None  # 共享数据上下文，由orchestrator设置
        self.task_name = self.__class__.__name__.replace('Task', '').lower()
        self.task_type = 'entity'  # 默认是实体任务
        
    def set_shared_context(self, context):
        """
        设置共享数据上下文
        
        Args:
            context: 共享数据上下文实例
        """
        self.shared_context = context
        logger.debug(f"Shared context set for task: {self.task_name}")
    
    def set_shared_data(self, key: str, data: Any, data_type: str = "unknown") -> bool:
        """
        设置共享数据
        
        Args:
            key (str): 数据键
            data (Any): 数据值
            data_type (str): 数据类型
            
        Returns:
            bool: 是否设置成功
        """
        if self.shared_context:
            return self.shared_context.set_data(key, data, data_type, self.task_name)
        else:
            logger.warning(f"No shared context available for task: {self.task_name}")
            return False
    
    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """
        获取共享数据
        
        Args:
            key (str): 数据键  
            default (Any): 默认值
            
        Returns:
            Any: 数据值或默认值
        """
        if self.shared_context:
            return self.shared_context.get_data(key, default, self.task_name)
        else:
            logger.warning(f"No shared context available for task: {self.task_name}")
            return default
    
    def has_shared_data(self, key: str) -> bool:
        """
        检查是否存在共享数据
        
        Args:
            key (str): 数据键
            
        Returns:
            bool: 是否存在
        """
        if self.shared_context:
            return self.shared_context.has_data(key)
        else:
            return False
        
    @abstractmethod
    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取数据的抽象方法
        
        Returns:
            List[Dict[str, Any]]: 获取到的数据列表
        """
        pass
    
    def get_dependencies(self) -> List[str]:
        """
        获取task依赖列表
        子类可以重写此方法来声明依赖关系
        
        Returns:
            List[str]: 依赖的task名称列表
        """
        return []
    
    def get_task_type(self) -> str:
        """
        获取任务类型
        
        Returns:
            str: 任务类型（'entity' 或 'relationship'）
        """
        return self.task_type
    
    def validate_config(self) -> bool:
        """
        验证配置是否正确
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['access_key_id', 'access_key_secret']
        for field in required_fields:
            if not self.config.get(field):
                logger.error(f"Missing required configuration: {field}")
                return False
        return True
    
    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return self.__class__.__name__
