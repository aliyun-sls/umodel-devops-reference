#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
共享数据上下文

提供task之间的数据共享和依赖管理功能
"""

import logging
import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class SharedDataContext:
    """
    共享数据上下文，管理task之间的数据共享
    """
    
    def __init__(self, cache_ttl: int = 300):
        """
        初始化共享数据上下文
        
        Args:
            cache_ttl (int): 缓存生存时间（秒），默认5分钟
        """
        self.cache_ttl = cache_ttl
        self._data = {}  # 存储共享数据
        self._metadata = {}  # 存储数据元信息（创建时间、类型等）
        self._dependencies = {}  # 存储task依赖关系
        self._lock = Lock()  # 线程安全锁
        
        logger.info(f"SharedDataContext initialized with TTL: {cache_ttl}s")
    
    def set_data(self, key: str, data: Any, data_type: str = "unknown", 
                 task_name: str = None, expire_at: datetime = None) -> bool:
        """
        设置共享数据
        
        Args:
            key (str): 数据键
            data (Any): 数据值
            data_type (str): 数据类型
            task_name (str): 设置数据的task名称
            expire_at (datetime): 过期时间，默认使用TTL
            
        Returns:
            bool: 是否设置成功
        """
        try:
            with self._lock:
                if expire_at is None:
                    expire_at = datetime.now() + timedelta(seconds=self.cache_ttl)
                
                self._data[key] = data
                self._metadata[key] = {
                    'created_at': datetime.now(),
                    'expire_at': expire_at,
                    'data_type': data_type,
                    'task_name': task_name,
                    'access_count': 0,
                    'size': self._calculate_size(data)
                }
                
                logger.debug(f"Set shared data: {key} (type: {data_type}, task: {task_name})")
                return True
                
        except Exception as e:
            logger.error(f"Error setting shared data {key}: {str(e)}")
            return False
    
    def get_data(self, key: str, default: Any = None, task_name: str = None) -> Any:
        """
        获取共享数据
        
        Args:
            key (str): 数据键
            default (Any): 默认值
            task_name (str): 获取数据的task名称
            
        Returns:
            Any: 数据值或默认值
        """
        try:
            with self._lock:
                # 检查数据是否存在
                if key not in self._data:
                    logger.debug(f"Shared data not found: {key}")
                    return default
                
                # 检查是否过期
                metadata = self._metadata.get(key, {})
                expire_at = metadata.get('expire_at')
                if expire_at and datetime.now() > expire_at:
                    logger.debug(f"Shared data expired: {key}")
                    self._remove_data(key)
                    return default
                
                # 更新访问统计
                if key in self._metadata:
                    self._metadata[key]['access_count'] += 1
                    self._metadata[key]['last_access'] = datetime.now()
                    self._metadata[key]['last_access_by'] = task_name
                
                logger.debug(f"Get shared data: {key} (by task: {task_name})")
                return self._data[key]
                
        except Exception as e:
            logger.error(f"Error getting shared data {key}: {str(e)}")
            return default
    
    def has_data(self, key: str) -> bool:
        """
        检查是否存在指定的共享数据
        
        Args:
            key (str): 数据键
            
        Returns:
            bool: 是否存在且未过期
        """
        try:
            with self._lock:
                if key not in self._data:
                    return False
                
                # 检查是否过期
                metadata = self._metadata.get(key, {})
                expire_at = metadata.get('expire_at')
                if expire_at and datetime.now() > expire_at:
                    self._remove_data(key)
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Error checking shared data {key}: {str(e)}")
            return False
    
    def remove_data(self, key: str) -> bool:
        """
        移除共享数据
        
        Args:
            key (str): 数据键
            
        Returns:
            bool: 是否移除成功
        """
        try:
            with self._lock:
                return self._remove_data(key)
                
        except Exception as e:
            logger.error(f"Error removing shared data {key}: {str(e)}")
            return False
    
    def _remove_data(self, key: str) -> bool:
        """
        内部方法：移除数据（不加锁）
        """
        removed = False
        if key in self._data:
            del self._data[key]
            removed = True
        if key in self._metadata:
            del self._metadata[key]
        
        if removed:
            logger.debug(f"Removed shared data: {key}")
        
        return removed
    
    def clear_expired(self) -> int:
        """
        清理过期数据
        
        Returns:
            int: 清理的数据项数量
        """
        try:
            with self._lock:
                expired_keys = []
                now = datetime.now()
                
                for key, metadata in self._metadata.items():
                    expire_at = metadata.get('expire_at')
                    if expire_at and now > expire_at:
                        expired_keys.append(key)
                
                # 移除过期数据
                for key in expired_keys:
                    self._remove_data(key)
                
                if expired_keys:
                    logger.info(f"Cleared {len(expired_keys)} expired shared data items")
                
                return len(expired_keys)
                
        except Exception as e:
            logger.error(f"Error clearing expired data: {str(e)}")
            return 0
    
    def clear_all(self) -> bool:
        """
        清理所有共享数据
        
        Returns:
            bool: 是否清理成功
        """
        try:
            with self._lock:
                count = len(self._data)
                self._data.clear()
                self._metadata.clear()
                
                logger.info(f"Cleared all {count} shared data items")
                return True
                
        except Exception as e:
            logger.error(f"Error clearing all data: {str(e)}")
            return False
    
    def set_task_dependency(self, task_name: str, depends_on: List[str]) -> bool:
        """
        设置task依赖关系
        
        Args:
            task_name (str): task名称
            depends_on (List[str]): 依赖的task列表
            
        Returns:
            bool: 是否设置成功
        """
        try:
            # 检查循环依赖
            if self._has_circular_dependency(task_name, depends_on):
                logger.error(f"Circular dependency detected for task: {task_name}")
                return False
            
            self._dependencies[task_name] = depends_on
            logger.info(f"Set dependencies for {task_name}: {depends_on}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting dependencies for {task_name}: {str(e)}")
            return False
    
    def get_execution_order(self, tasks: List[str]) -> List[str]:
        """
        根据依赖关系计算task执行顺序
        
        Args:
            tasks (List[str]): 要执行的task列表
            
        Returns:
            List[str]: 排序后的task执行顺序
        """
        try:
            # 拓扑排序算法
            visited = set()
            temp_visited = set()
            result = []
            
            def dfs(task: str):
                if task in temp_visited:
                    raise ValueError(f"Circular dependency detected involving task: {task}")
                if task in visited:
                    return
                
                temp_visited.add(task)
                
                # 访问所有依赖的task
                dependencies = self._dependencies.get(task, [])
                for dep in dependencies:
                    if dep in tasks:  # 只考虑需要执行的task
                        dfs(dep)
                
                temp_visited.remove(task)
                visited.add(task)
                result.append(task)
            
            # 对所有task进行深度优先搜索
            for task in tasks:
                if task not in visited:
                    dfs(task)
            
            logger.info(f"Calculated execution order: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error calculating execution order: {str(e)}")
            return tasks  # 返回原始顺序作为fallback
    
    def _has_circular_dependency(self, task_name: str, depends_on: List[str]) -> bool:
        """
        检查是否存在循环依赖
        """
        try:
            # 深度优先搜索检测循环
            visited = set()
            
            def dfs(current: str, path: Set[str]) -> bool:
                if current in path:
                    return True  # 发现循环
                if current in visited:
                    return False
                
                visited.add(current)
                path.add(current)
                
                # 检查当前task的依赖
                current_deps = self._dependencies.get(current, [])
                if task_name in current_deps:
                    # 如果当前task依赖于我们要设置的task，检查新的依赖关系
                    for dep in depends_on:
                        if dfs(dep, path.copy()):
                            return True
                else:
                    # 正常检查依赖关系
                    for dep in current_deps:
                        if dfs(dep, path.copy()):
                            return True
                
                path.remove(current)
                return False
            
            # 检查新的依赖是否会造成循环
            for dep in depends_on:
                if dfs(dep, {task_name}):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking circular dependency: {str(e)}")
            return True  # 保守策略，有错误时认为存在循环依赖
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取共享数据上下文状态
        
        Returns:
            Dict[str, Any]: 状态信息
        """
        try:
            with self._lock:
                now = datetime.now()
                active_data = {}
                expired_data = {}
                
                for key, metadata in self._metadata.items():
                    expire_at = metadata.get('expire_at')
                    is_expired = expire_at and now > expire_at
                    
                    info = {
                        'data_type': metadata.get('data_type'),
                        'task_name': metadata.get('task_name'),
                        'created_at': metadata.get('created_at').isoformat() if metadata.get('created_at') else None,
                        'expire_at': expire_at.isoformat() if expire_at else None,
                        'access_count': metadata.get('access_count', 0),
                        'size': metadata.get('size', 0)
                    }
                    
                    if is_expired:
                        expired_data[key] = info
                    else:
                        active_data[key] = info
                
                return {
                    'cache_ttl': self.cache_ttl,
                    'active_data_count': len(active_data),
                    'expired_data_count': len(expired_data),
                    'total_size': sum(meta.get('size', 0) for meta in self._metadata.values()),
                    'active_data': active_data,
                    'expired_data': expired_data,
                    'dependencies': self._dependencies.copy(),
                    'timestamp': now.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting status: {str(e)}")
            return {'error': str(e)}
    
    def _calculate_size(self, data: Any) -> int:
        """
        估算数据大小（简单实现）
        """
        try:
            import sys
            return sys.getsizeof(data)
        except:
            return 0
    
    def __repr__(self) -> str:
        return f"SharedDataContext(items={len(self._data)}, ttl={self.cache_ttl}s)"
