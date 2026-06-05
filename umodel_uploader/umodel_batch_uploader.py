# -*- coding: utf-8 -*-
"""
UModel 批量上传工具 - 简化版本
支持扫描指定目录下的所有 umodel YAML 文件并批量上传到阿里云
"""
import os
import sys
import json
from typing import List, Dict, Any
from pathlib import Path

# 尝试导入yaml库，如果失败则提示安装
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("❌ 错误: 未找到PyYAML库！")
    print("请运行以下命令安装: pip install pyyaml")
    print("umodel数据包含复杂的嵌套结构，需要使用PyYAML进行正确解析")
    import sys
    sys.exit(1)

from alibabacloud_cms20240330.client import Client as Cms20240330Client
from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_cms20240330 import models as cms_20240330_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient


class UModelBatchUploader:
    """UModel 批量上传器"""
    
    def __init__(self, endpoint: str = 'metrics.cn-hongkong.aliyuncs.com', workspace: str = None):
        """
        初始化上传器
        
        Args:
            endpoint: 阿里云API端点地址
            workspace: UModel工作空间名称
        """
        self.endpoint = endpoint
        self.workspace = workspace
        self.client = self._create_client()
        
    def _create_client(self) -> Cms20240330Client:
        """
        使用凭据初始化账号Client
        
        Returns:
            Client: 云监控API客户端
        """
        try:
            credential = CredentialClient()
            config = open_api_models.Config(credential=credential)
            config.endpoint = self.endpoint
            return Cms20240330Client(config)
        except Exception as e:
            print(f"❌ 创建客户端失败: {e}")
            print("请检查阿里云凭据配置是否正确")
            raise
    
    def _is_umodel_file(self, file_path: str) -> bool:
        """
        判断文件是否为有效的umodel文件
        """
        if not file_path.endswith('.yaml') and not file_path.endswith('.yml'):
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
                
            # 检查是否包含umodel必需字段
            if not isinstance(content, dict):
                return False
                
            # 检查kind字段
            kind = content.get('kind')
            if kind not in ['entity_set', 'entity_set_link']:
                return False
                
            # 检查必需的字段
            if 'metadata' not in content or 'spec' not in content:
                return False
                
            return True
            
        except Exception as e:
            print(f"警告: 读取文件 {file_path} 时出错: {e}")
            return False
    
    def _load_umodel_data(self, file_path: str) -> Dict[str, Any]:
        """
        加载umodel数据文件
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _upload_single_umodel(self, file_path: str, umodel_data: Dict[str, Any]) -> bool:
        """
        上传单个umodel数据文件
        """
        try:
            # 构建请求参数
            upsert_request = cms_20240330_models.UpsertUmodelDataRequest()
            
            # 设置请求参数：elements是数组格式，包含umodel数据对象
            upsert_request.elements = [umodel_data]
            
            # 设置操作方法
            upsert_request.method = "upsert"
            
            # 设置名称
            if 'metadata' in umodel_data and 'name' in umodel_data['metadata']:
                upsert_request.name = umodel_data['metadata']['name']
            
            # 运行时选项和请求头
            runtime = util_models.RuntimeOptions()
            headers = {}
            
            # 调用API上传数据
            workspace_param = self.workspace if self.workspace else ""
            response = self.client.upsert_umodel_data_with_options(
                workspace_param, upsert_request, headers, runtime
            )
            
            print(f"✅ 成功上传: {file_path}")
            return True
            
        except Exception as error:
            print(f"❌ 上传失败: {file_path}")
            print(f"   错误信息: {error}")
            return False
    
    def scan_directory(self, directory: str) -> List[str]:
        """
        扫描目录下的所有umodel文件
        """
        umodel_files = []
        directory_path = Path(directory)
        
        if not directory_path.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
            
        if not directory_path.is_dir():
            raise NotADirectoryError(f"路径不是目录: {directory}")
        
        print(f"🔍 正在扫描目录: {directory}")
        
        # 递归遍历目录
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                if self._is_umodel_file(file_path):
                    umodel_files.append(file_path)
                    
        print(f"📁 找到 {len(umodel_files)} 个umodel文件")
        return umodel_files
    
    def batch_upload(self, directory: str, dry_run: bool = False) -> Dict[str, int]:
        """
        批量上传目录下的所有umodel文件
        """
        umodel_files = self.scan_directory(directory)
        
        if not umodel_files:
            print("⚠️  未找到任何umodel文件")
            return {'success': 0, 'failed': 0, 'total': 0}
        
        success_count = 0
        failed_count = 0
        
        print(f"\n{'=' * 50}")
        if dry_run:
            print("🔎 预运行模式 - 不会实际上传数据")
        else:
            print("🚀 开始批量上传umodel数据...")
        print(f"{'=' * 50}")
        
        for i, file_path in enumerate(umodel_files, 1):
            print(f"\n[{i}/{len(umodel_files)}] 处理文件: {os.path.basename(file_path)}")
            
            try:
                # 加载文件数据
                umodel_data = self._load_umodel_data(file_path)
                
                if dry_run:
                    # 预运行模式：只验证文件格式
                    kind = umodel_data.get('kind', 'unknown')
                    name = umodel_data.get('metadata', {}).get('name', 'unknown')
                    print(f"✅ 文件格式验证通过: {kind} - {name}")
                    success_count += 1
                else:
                    # 实际上传
                    if self._upload_single_umodel(file_path, umodel_data):
                        success_count += 1
                    else:
                        failed_count += 1
                        
            except Exception as e:
                print(f"❌ 处理文件时出错: {e}")
                failed_count += 1
        
        # 输出统计结果
        total_count = len(umodel_files)
        print(f"\n{'=' * 50}")
        print("📊 统计结果:")
        print(f"   总计文件: {total_count}")
        print(f"   成功: {success_count}")
        print(f"   失败: {failed_count}")
        if total_count > 0:
            print(f"   成功率: {(success_count/total_count*100):.1f}%")
        print(f"{'=' * 50}")
        
        return {
            'success': success_count,
            'failed': failed_count,
            'total': total_count
        }


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python umodel_batch_uploader.py <目录路径> [选项]")
        print("")
        print("选项:")
        print("  --dry-run          预运行模式，只验证文件不实际上传")
        print("  --endpoint <端点>  指定API端点")
        print("  --workspace <名称> 指定UModel工作空间名称")
        print("")
        print("示例:")
        print("  python umodel_batch_uploader.py ./umodel --dry-run")
        print("  python umodel_batch_uploader.py ./umodel --workspace my-workspace")
        return
    
    directory = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    
    # 解析endpoint参数
    endpoint = 'metrics.cn-hongkong.aliyuncs.com'
    if '--endpoint' in sys.argv:
        endpoint_index = sys.argv.index('--endpoint')
        if endpoint_index + 1 < len(sys.argv):
            endpoint = sys.argv[endpoint_index + 1]
    
    # 解析workspace参数
    workspace = None
    if '--workspace' in sys.argv:
        workspace_index = sys.argv.index('--workspace')
        if workspace_index + 1 < len(sys.argv):
            workspace = sys.argv[workspace_index + 1]
    
    try:
        # 创建上传器并执行批量上传
        uploader = UModelBatchUploader(endpoint=endpoint, workspace=workspace)
        
        if workspace:
            print(f"🏢 使用工作空间: {workspace}")
        
        result = uploader.batch_upload(directory, dry_run=dry_run)
        
        # 根据结果设置退出码
        if result['failed'] == 0:
            sys.exit(0)  # 成功
        else:
            sys.exit(1)  # 有失败的文件
            
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()