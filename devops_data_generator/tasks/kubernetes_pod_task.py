#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kubernetes Pod 数据获取任务

支持两种数据源获取 k8s.pod 实体数据：
1. 通过阿里云 CMS 2.0 API 获取
2. 通过 Kubernetes Service API 直接获取

包括Pod的基本信息和容器镜像信息。
"""

import json
import logging
import time
import hashlib
from typing import Dict, List, Any

try:
    from alibabacloud_cms20240330.client import Client as Cms20240330Client
    from alibabacloud_credentials.client import Config as credentialConfig
    from alibabacloud_credentials.client import Client as CredentialClient
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_cms20240330 import models as cms_20240330_models
    from alibabacloud_tea_util import models as util_models
    CMS_SDK_AVAILABLE = True
except ModuleNotFoundError:
    Cms20240330Client = None
    credentialConfig = None
    CredentialClient = None
    open_api_models = None
    cms_20240330_models = None
    util_models = None
    CMS_SDK_AVAILABLE = False

try:
    from kubernetes import client as k8s_client, config as k8s_config
    from kubernetes.client.rest import ApiException
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("kubernetes library not available, K8S API support disabled")

from .base_task import BaseTask

logger = logging.getLogger(__name__)


class KubernetesPodTask(BaseTask):
    """
    Kubernetes Pod 数据获取任务
    
    支持两种数据源：
    1. CMS API - 通过阿里云 CMS 2.0 API 获取 k8s.pod 实体数据
    2. K8S API - 通过 Kubernetes Service API 直接获取 Pod 数据
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Kubernetes Pod 任务
        
        Args:
            config (Dict[str, Any]): 配置信息
                - data_source (str): 数据源类型 'cms' 或 'k8s'，默认 'k8s'
                - cluster_id (str): 集群ID，用于生成Entity ID
                - endpoint (str): CMS endpoint (仅CMS模式需要)
                - workspace (str): CMS workspace (仅CMS模式需要)  
                - namespace_filter (str): 过滤的命名空间
                - kubeconfig_path (str): kubeconfig文件路径 (仅K8S模式需要，可选)
                - k8s_context (str): K8S上下文名称 (仅K8S模式需要，可选)
        """
        super().__init__(config)
        self.task_type = 'entity'  # 这是一个实体任务
        
        # 数据源配置
        self.data_source = config.get('data_source', 'k8s').lower()  # 'cms' 或 'k8s'，默认k8s
        self.namespace_filter = config.get('namespace_filter', 'apm-demo')
        self.cluster_id = config.get('cluster_id', 'default-cluster')  # 集群ID，用于Entity ID生成
        
        # CMS 配置
        self.endpoint = config.get('endpoint', 'metrics.cn-hongkong.aliyuncs.com')
        self.workspace = config.get('workspace', 'o11y-aiops-demo-cn-hongkong')
        
        # K8S 配置
        self.kubeconfig_path = config.get('kubeconfig_path')  # 可选，默认使用集群内配置或 ~/.kube/config
        self.k8s_context = config.get('k8s_context')  # 可选，指定K8S上下文
        
        logger.info(f"KubernetesPodTask initialized with data_source={self.data_source}, cluster_id={self.cluster_id}")
    
    def get_dependencies(self) -> List[str]:
        """
        获取依赖任务列表
        
        Returns:
            List[str]: 依赖的task名称列表，Pod任务不依赖其他任务
        """
        return []

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        获取 Kubernetes Pod 数据
        
        Returns:
            List[Dict[str, Any]]: Pod 数据列表
            
        Raises:
            RuntimeError: 数据获取失败
        """
        if not self.validate_config():
            logger.warning("Skipping kubernetes_pod fetch because configuration is invalid or incomplete")
            return []

        try:
            if self.data_source == 'cms':
                return self._fetch_data_from_cms()
            elif self.data_source == 'k8s':
                return self._fetch_data_from_k8s()
            else:
                raise ValueError(f"Unsupported data source: {self.data_source}")
            
        except Exception as e:
            error_msg = f"Error fetching pod data from {self.data_source}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _fetch_data_from_cms(self) -> List[Dict[str, Any]]:
        """
        从CMS API获取Pod数据
        
        Returns:
            List[Dict[str, Any]]: Pod 数据列表
        """
        # 创建 CMS 客户端
        client = self._create_cms_client()
        
        # 调用 API 获取 Pod 数据
        raw_data = self._get_pod_data_from_cms(client)
        
        # 处理和转换数据
        processed_pods = self._process_cms_pod_data(raw_data)
        
        logger.info(f"Successfully fetched {len(processed_pods)} pods from CMS API")
        
        # 存储到共享数据上下文
        self.set_shared_data("k8s_pod_raw_data", processed_pods, "pod_data")
        
        return processed_pods

    def _fetch_data_from_k8s(self) -> List[Dict[str, Any]]:
        """
        从K8S API获取Pod数据
        
        Returns:
            List[Dict[str, Any]]: Pod 数据列表
        """
        # 创建 K8S 客户端
        api_instance = self._create_k8s_client()
        
        # 调用 API 获取 Pod 数据
        pod_list = self._get_pod_data_from_k8s(api_instance)
        
        # 处理和转换数据
        processed_pods = self._process_k8s_pod_data(pod_list)
        
        logger.info(f"Successfully fetched {len(processed_pods)} pods from K8S API")
        
        # 存储到共享数据上下文
        self.set_shared_data("k8s_pod_raw_data", processed_pods, "pod_data")
        
        return processed_pods

    def _create_cms_client(self):
        """
        创建 CMS 客户端
        
        Returns:
            Cms20240330Client: CMS 客户端实例
        """
        try:
            creConfig = credentialConfig(
                type='access_key',
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret
            )
            credential = CredentialClient(creConfig)
            config = open_api_models.Config(
                endpoint=self.endpoint,
                credential=credential
            )
            
            return Cms20240330Client(config)
            
        except Exception as e:
            logger.error(f"Error creating CMS client: {str(e)}")
            raise

    def _create_k8s_client(self):
        """
        创建 K8S 客户端
        
        Returns:
            k8s_client.CoreV1Api: K8S Core V1 API 客户端实例
            
        Raises:
            RuntimeError: 客户端创建失败
        """
        try:
            # 加载K8S配置
            if self.kubeconfig_path:
                # 使用指定的kubeconfig文件
                k8s_config.load_kube_config(
                    config_file=self.kubeconfig_path,
                    context=self.k8s_context
                )
                logger.info(f"Loaded K8S config from file: {self.kubeconfig_path}")
            else:
                try:
                    # 尝试使用集群内配置
                    k8s_config.load_incluster_config()
                    logger.info("Loaded K8S in-cluster config")
                except k8s_config.ConfigException:
                    # 回退到默认kubeconfig
                    k8s_config.load_kube_config(context=self.k8s_context)
                    logger.info("Loaded K8S config from default location")
            
            # 创建Core V1 API客户端
            return k8s_client.CoreV1Api()
            
        except Exception as e:
            error_msg = f"Error creating K8S client: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _get_pod_data_from_cms(self, client) -> Dict[str, Any]:
        """
        从 CMS API 获取 Pod 数据
        
        Args:
            client (Cms20240330Client): CMS 客户端
            
        Returns:
            Dict[str, Any]: API 响应数据
        """
        try:
            # 构建查询语句
            query = f".entity with(domain='k8s', type='k8s.pod', query='namespace: {self.namespace_filter}') |project __entity_id__, containers, __domain__, __entity_type__"
            
            # 计算时间戳：最近5分钟
            current_time = int(time.time())
            five_minutes_ago = current_time - (5 * 60)  # 5分钟前
            
            logger.info(f"Querying CMS for Pod data in time range: {five_minutes_ago} to {current_time} (last 5 minutes)")
            
            # 创建请求头和请求体
            headers = cms_20240330_models.GetEntityStoreDataHeaders()
            request = cms_20240330_models.GetEntityStoreDataRequest(
                from_=five_minutes_ago,  # 5分钟前
                to=current_time,         # 当前时间
                query=query
            )
            runtime = util_models.RuntimeOptions()
            
            # 调用 API
            response = client.get_entity_store_data_with_options(
                self.workspace,
                request,
                headers,
                runtime
            )
            
            if response.status_code == 200 and response.body:
                data = response.body.to_map()
                return data
            else:
                logger.warning(f"CMS API returned status {response.status_code}")
                return {"data": {"data": [], "header": []}}
                
        except Exception as e:
            logger.error(f"Error calling CMS API: {str(e)}")
            raise RuntimeError(f"Failed to get pod data from CMS: {str(e)}") from e

    def _get_pod_data_from_k8s(self, api_instance):
        """
        从 K8S API 获取 Pod 数据
        
        Args:
            api_instance (k8s_client.CoreV1Api): K8S Core V1 API 客户端
            
        Returns:
            k8s_client.V1PodList: K8S Pod 列表对象
            
        Raises:
            RuntimeError: API调用失败
        """
        try:
            logger.info(f"Querying K8S API for pods in namespace: {self.namespace_filter}")
            
            # 调用 K8S API 获取指定命名空间的 Pod 列表
            pod_list = api_instance.list_namespaced_pod(
                namespace=self.namespace_filter,
                _request_timeout=30  # 30秒超时
            )
            
            logger.info(f"K8S API returned {len(pod_list.items)} pods")
            return pod_list
            
        except ApiException as e:
            error_msg = f"K8S API exception: {e.status} {e.reason}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Error calling K8S API: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _process_cms_pod_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理来自CMS的Pod数据
        
        Args:
            raw_data (Dict[str, Any]): CMS API 返回的原始数据
            
        Returns:
            List[Dict[str, Any]]: 处理后的 Pod 数据列表
        """
        processed_pods = []
        
        try:
            data_section = raw_data.get('data', {})
            rows = raw_data.get('data', [])
            headers = raw_data.get('header', [])
            
            if not rows or not headers:
                logger.warning("No pod data found in CMS response")
                return []
            
            logger.info(f"Processing {len(rows)} pods from CMS")
            
            # 确定列的索引
            entity_id_idx = headers.index('__entity_id__') if '__entity_id__' in headers else 0
            containers_idx = headers.index('containers') if 'containers' in headers else 1
            domain_idx = headers.index('__domain__') if '__domain__' in headers else 2
            entity_type_idx = headers.index('__entity_type__') if '__entity_type__' in headers else 3
            
            for row in rows:
                if not row or len(row) < 4:
                    logger.warning(f"Invalid row data: {row}")
                    continue
                
                try:
                    pod_data = self._process_single_pod(
                        row, entity_id_idx, containers_idx, domain_idx, entity_type_idx
                    )
                    if pod_data:
                        processed_pods.append(pod_data)
                        
                except Exception as e:
                    logger.error(f"Error processing pod row {row}: {str(e)}")
                    continue
            
            return processed_pods
            
        except Exception as e:
            logger.error(f"Error processing pod data: {str(e)}")
            return []

    def _process_single_pod(
        self, 
        row: List[str], 
        entity_id_idx: int, 
        containers_idx: int, 
        domain_idx: int, 
        entity_type_idx: int
    ) -> Dict[str, Any]:
        """
        处理单个 Pod 数据
        
        Args:
            row (List[str]): 单行数据
            entity_id_idx (int): 实体ID列索引
            containers_idx (int): 容器列索引
            domain_idx (int): 域列索引
            entity_type_idx (int): 实体类型列索引
            
        Returns:
            Dict[str, Any]: 处理后的 Pod 数据
        """
        try:
            original_entity_id = row[entity_id_idx]
            containers_json = row[containers_idx]
            domain = row[domain_idx]
            entity_type = row[entity_type_idx]
            
            # 从原始entity_id中提取pod名称和命名空间信息
            # 通常CMS返回的entity_id格式类似：namespace.podname 或 直接包含这些信息
            pod_name = ""
            namespace = self.namespace_filter
            
            # 尝试从entity_id中提取pod信息
            if "." in original_entity_id:
                parts = original_entity_id.split(".")
                if len(parts) >= 2:
                    namespace = parts[0] if parts[0] else self.namespace_filter
                    pod_name = ".".join(parts[1:])  # 支持pod名称中包含点号
            else:
                pod_name = original_entity_id
            
            # 解析容器 JSON 数据
            containers = []
            try:
                containers = json.loads(containers_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid containers JSON for pod {pod_name}: {containers_json}, error: {str(e)}")
                containers = []
            
            # 提取镜像信息
            images = []
            container_names = []
            
            for container in containers:
                if isinstance(container, dict):
                    image = container.get('image', '')
                    name = container.get('name', '')
                    if image:
                        images.append(image)
                    if name:
                        container_names.append(name)
            
            # 生成新的Entity ID，遵循规定规则
            entity_id = self._generate_pod_entity_id(self.cluster_id, namespace, pod_name)
            
            # 构建 Pod 数据
            pod_data = {
                'pod_id': entity_id,  # 使用新生成的entity_id
                'entity_id': entity_id,
                'domain': domain,
                'entity_type': entity_type,
                'containers': containers,
                'images': images,
                'container_names': container_names,
                'image_count': len(images),
                'container_count': len(containers),
                'namespace': namespace,
                'pod_name': pod_name,
                'original_entity_id': original_entity_id  # 保留原始ID用于调试
            }
            
            logger.debug(f"Processed CMS pod {pod_name} with {len(images)} images, entity_id: {entity_id}")
            return pod_data
            
        except Exception as e:
            logger.error(f"Error processing single pod: {str(e)}")
            return {}

    def _process_k8s_pod_data(self, pod_list) -> List[Dict[str, Any]]:
        """
        处理来自K8S API的Pod数据
        
        Args:
            pod_list: K8S API 返回的 Pod 列表对象
            
        Returns:
            List[Dict[str, Any]]: 处理后的 Pod 数据列表
        """
        processed_pods = []
        
        try:
            logger.info(f"Processing {len(pod_list.items)} pods from K8S API")
            
            for pod in pod_list.items:
                try:
                    pod_data = self._process_single_k8s_pod(pod)
                    if pod_data:
                        processed_pods.append(pod_data)
                        
                except Exception as e:
                    logger.error(f"Error processing K8S pod {pod.metadata.name}: {str(e)}")
                    continue
            
            return processed_pods
            
        except Exception as e:
            logger.error(f"Error processing K8S pod data: {str(e)}")
            return []

    def _process_single_k8s_pod(self, pod) -> Dict[str, Any]:
        """
        处理单个 K8S Pod 数据
        
        Args:
            pod: K8S Pod 对象
            
        Returns:
            Dict[str, Any]: 处理后的 Pod 数据
        """
        try:
            # 获取Pod基本信息
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            
            # 生成Pod Entity ID，遵循规定规则
            entity_id = self._generate_pod_entity_id(self.cluster_id, namespace, pod_name)
            
            # 提取容器信息
            containers = []
            images = []
            container_names = []
            
            # 处理容器列表
            if pod.spec.containers:
                for container in pod.spec.containers:
                    container_info = {
                        'name': container.name,
                        'image': container.image,
                    }
                    containers.append(container_info)
                    
                    # 提取镜像和容器名
                    if container.image:
                        images.append(container.image)
                    if container.name:
                        container_names.append(container.name)
            
            # 处理初始化容器 (如果有)
            if pod.spec.init_containers:
                for init_container in pod.spec.init_containers:
                    container_info = {
                        'name': init_container.name,
                        'image': init_container.image,
                    }
                    containers.append(container_info)
                    
                    if init_container.image:
                        images.append(init_container.image)
                    if init_container.name:
                        container_names.append(init_container.name)
            
            # 构建 Pod 数据 (保持与CMS格式一致)
            pod_data = {
                'pod_id': entity_id,  # 使用规范的Entity ID
                'entity_id': entity_id,
                'domain': 'k8s',  # K8S域
                'entity_type': 'k8s.pod',  # 实体类型
                'containers': containers,
                'images': list(set(images)),  # 去重
                'container_names': list(set(container_names)),  # 去重
                'image_count': len(set(images)),
                'container_count': len(containers),
                'namespace': namespace,
                # 额外的K8S特有字段
                'pod_name': pod_name,
                'pod_uid': pod.metadata.uid,
                'node_name': pod.spec.node_name if pod.spec.node_name else '',
                'phase': pod.status.phase if pod.status.phase else 'Unknown',
                'creation_timestamp': pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
            }
            
            logger.debug(f"Processed K8S pod {pod_name} with {len(set(images))} images, entity_id: {entity_id}")
            return pod_data
            
        except Exception as e:
            logger.error(f"Error processing single K8S pod: {str(e)}")
            return {}

    def _generate_pod_entity_id(self, cluster_id: str, namespace: str, pod_name: str) -> str:
        """
        生成Pod Entity ID
        
        规则: lower(to_hex(md5(cast(concat(cluster_id,'Pod',namespace,name) as varbinary))))
        
        Args:
            cluster_id (str): 集群ID
            namespace (str): Pod命名空间
            pod_name (str): Pod名称
            
        Returns:
            str: 生成的Pod Entity ID
        """
        try:
            # 构建字符串：cluster_id + 'Pod' + namespace + name
            id_string = f"{cluster_id}Pod{namespace}{pod_name}"
            
            # 计算MD5哈希并转换为小写十六进制
            md5_hash = hashlib.md5(id_string.encode('utf-8')).hexdigest().lower()
            
            logger.debug(f"Generated Pod Entity ID '{md5_hash}' from string '{id_string}'")
            return md5_hash
            
        except Exception as e:
            logger.error(f"Error generating Pod Entity ID: {str(e)}")
            # 回退方案：简单拼接
            return f"{cluster_id}.{namespace}.{pod_name}".replace(' ', '_')

    def validate_config(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 配置是否有效
        """
        # 验证通用配置
        if not self.namespace_filter:
            logger.warning("namespace_filter not configured")
            return False
        
        if not self.cluster_id:
            logger.warning("cluster_id not configured")
            return False
        
        # 根据数据源验证不同配置
        if self.data_source == 'cms':
            # 验证CMS配置
            if not CMS_SDK_AVAILABLE:
                logger.warning("CMS SDK dependencies are not installed")
                return False

            if not self.workspace:
                logger.warning("CMS workspace not configured")
                return False
            
            if not self.endpoint:
                logger.warning("CMS endpoint not configured")
                return False

            if not self.access_key_id or not self.access_key_secret:
                logger.warning("CMS access key is not configured")
                return False
                
            logger.info(f"CMS config validation passed: workspace={self.workspace}, endpoint={self.endpoint}, cluster_id={self.cluster_id}")
            
        elif self.data_source == 'k8s':
            # 验证K8S配置
            if not K8S_AVAILABLE:
                logger.warning("K8S data source selected but kubernetes library not available")
                return False
            
            # 对于K8S，kubeconfig_path是可选的，会自动尝试多种配置方式
            logger.info(f"K8S config validation passed: kubeconfig_path={self.kubeconfig_path}, context={self.k8s_context}, cluster_id={self.cluster_id}")
        
        else:
            logger.warning(f"Invalid data_source: {self.data_source}")
            return False
        
        logger.info(f"Config validation passed for data_source={self.data_source}, namespace={self.namespace_filter}, cluster_id={self.cluster_id}")
        return True

    def get_task_name(self) -> str:
        """
        获取任务名称
        
        Returns:
            str: 任务名称
        """
        return "kubernetes_pod"
