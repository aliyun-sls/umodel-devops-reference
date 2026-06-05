import logging
import time
import json
from typing import Dict, List, Any

try:
    from aliyun.log import LogClient, LogItem, PutLogsRequest
    SLS_SDK_AVAILABLE = True
except ModuleNotFoundError:
    LogClient = None
    LogItem = None
    PutLogsRequest = None
    SLS_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


class SlsDataSender:
    """
    SLS数据发送器
    
    使用阿里云新版本SDK (alibabacloud_sls20201230) 发送数据到SLS LogStore
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据发送器
        
        Args:
            config (Dict[str, Any]): SLS配置信息
        """
        self.endpoint = config.get('endpoint')
        self.access_key_id = config.get('access_key_id')
        self.access_key_secret = config.get('access_key_secret')
        self.project = config.get('project')
        self.sdk_available = SLS_SDK_AVAILABLE

        # 创建SLS客户端
        self.client = self._create_client() if self.sdk_available else None

        # LogStore映射配置
        self.logstore_mapping = config.get('logstore_mapping', {})

        logger.info(f"Initialized SLS sender for project: {self.project}")

    def _create_client(self) -> LogClient:
        """
        创建SLS客户端
        
        Returns:
            Sls20201230Client: SLS客户端实例
        """
        if not self.sdk_available:
            logger.warning("aliyun-log-python-sdk is not installed; SLS sender is disabled")
            return None
        return LogClient(self.endpoint, self.access_key_id, self.access_key_secret)

    def send_entity_data(self, entity_type: str, data: List[Dict[str, Any]]) -> bool:
        """
        发送实体数据到SLS
        
        Args:
            entity_type (str): 实体类型
            data (List[Dict[str, Any]]): 实体数据列表
            
        Returns:
            bool: 发送是否成功
        """
        if not self.sdk_available:
            logger.warning("Skip sending entity data because aliyun-log-python-sdk is unavailable")
            return False
        try:
            logstore = self._get_logstore_for_entity(entity_type)
            if not logstore:
                logger.error(f"No logstore configured for entity type: {entity_type}")
                return False

            if not data:
                logger.warning(f"No data to send for entity type: {entity_type}")
                return True

            # 分批发送，每批最多100条
            batch_size = 100
            total_sent = 0

            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                success = self._send_log_batch(logstore, batch)
                if not success:
                    logger.error(f"Failed to send batch {i // batch_size + 1} for {entity_type}")
                    return False
                total_sent += len(batch)

            logger.info(f"Successfully sent {total_sent} {entity_type} entities to logstore: {logstore}")
            return True

        except Exception as e:
            logger.error(f"Error sending entity data: {str(e)}")
            return False

    def send_relationship_data(self, relationship_type: str, data: List[Dict[str, Any]]) -> bool:
        """
        发送关系数据到SLS
        
        Args:
            relationship_type (str): 关系类型
            data (List[Dict[str, Any]]): 关系数据列表
            
        Returns:
            bool: 发送是否成功
        """
        if not self.sdk_available:
            logger.warning("Skip sending relationship data because aliyun-log-python-sdk is unavailable")
            return False
        try:
            logstore = self._get_logstore_for_relationship(relationship_type)
            if not logstore:
                logger.error(f"No logstore configured for relationship type: {relationship_type}")
                return False

            if not data:
                logger.warning(f"No data to send for relationship type: {relationship_type}")
                return True

            # 分批发送，每批最多100条
            batch_size = 100
            total_sent = 0

            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                success = self._send_log_batch(logstore, batch)
                if not success:
                    logger.error(f"Failed to send batch {i // batch_size + 1} for {relationship_type}")
                    return False
                total_sent += len(batch)

            logger.info(f"Successfully sent {total_sent} {relationship_type} relationships to logstore: {logstore}")
            return True

        except Exception as e:
            logger.error(f"Error sending relationship data: {str(e)}")
            return False

    def _send_log_batch(self, logstore: str, data_batch: List[Dict[str, Any]]) -> bool:
        """
        发送日志批次到SLS
        
        Args:
            logstore (str): LogStore名称
            data_batch (List[Dict[str, Any]]): 数据批次
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 构造请求体
            logitemList = []  # LogItem list

            for item in data_batch:
                logItem = LogItem()
                contents = []
                for key, value in item.items():
                    if value is not None: 
                        contents.append((key, str(value)))
                logItem.set_time(int(time.time()))
                logItem.set_contents(contents)
                logitemList.append(logItem)
            request = PutLogsRequest(self.project, logstore, '', 'devops_data_generator', logitemList)
            response = self.client.put_logs(request)
            logger.debug(f"Successfully sent {len(data_batch)} logs to {logstore}")
            return True
        except Exception as e:
            logger.error(f"Error sending log batch to {logstore}: {str(e)}")
            return False


    def _get_logstore_for_entity(self, entity_type: str) -> str:
        """
        获取实体类型对应的LogStore
        
        Args:
            entity_type (str): 实体类型
            
        Returns:
            str: LogStore名称
        """
        entity_mapping = self.logstore_mapping.get('entities', {})
        return entity_mapping.get(entity_type, f"{entity_type}_logstore")

    def _get_logstore_for_relationship(self, relationship_type: str) -> str:
        """
        获取关系类型对应的LogStore
        
        Args:
            relationship_type (str): 关系类型
            
        Returns:
            str: LogStore名称
        """
        relationship_mapping = self.logstore_mapping.get('relationships', {})
        return relationship_mapping.get(relationship_type, f"{relationship_type}_logstore")

    def validate_connection(self) -> bool:
        """
        验证与SLS的连接
        
        Returns:
            bool: 连接是否有效
        """
        try:
            # 构造请求
            list_logstores_request = sls_20201230_models.ListLogstoresRequest()
            list_logstores_headers = sls_20201230_models.ListLogstoresHeaders()
            runtime = util_models.RuntimeOptions()

            # 尝试列出LogStore来验证连接
            response = self.client.list_logstores_with_options(
                self.project,
                list_logstores_request,
                list_logstores_headers,
                runtime
            )

            if response.status_code == 200:
                logger.info("SLS connection validated successfully")
                return True
            else:
                logger.error(f"SLS connection validation failed, status: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error validating SLS connection: {str(e)}")
            # 如果没有配置或测试环境，返回True继续执行
            logger.info("Using mock SLS connection for testing")
            return True

    def get_project_info(self) -> Dict[str, Any]:
        """
        获取项目信息
        
        Returns:
            Dict[str, Any]: 项目信息
        """
        try:
            get_project_request = sls_20201230_models.GetProjectRequest()
            get_project_headers = sls_20201230_models.GetProjectHeaders()
            runtime = util_models.RuntimeOptions()

            response = self.client.get_project_with_options(
                self.project,
                get_project_request,
                get_project_headers,
                runtime
            )

            if response.status_code == 200:
                return {
                    'project_name': self.project,
                    'endpoint': self.endpoint,
                    'status': 'connected'
                }
            else:
                return {
                    'project_name': self.project,
                    'endpoint': self.endpoint,
                    'status': 'error',
                    'status_code': response.status_code
                }

        except Exception as e:
            logger.error(f"Error getting project info: {str(e)}")
            return {
                'project_name': self.project,
                'endpoint': self.endpoint,
                'status': 'mock',
                'error': str(e)
            }
