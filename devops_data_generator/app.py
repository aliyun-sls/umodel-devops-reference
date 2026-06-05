#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DevOps数据生成器Flask应用

根据需求文档实现的完整数据生成器，包含：
1. Task: 通过阿里云OpenAPI获取各种数据
2. SlsDataGenerator: 将Task的数据根据配置模板映射成SLS数据结构
3. SlsDataSender: 将LogItem发送到不同的LogStore中

Flask API端点：
- POST /invoke: 执行数据生成任务
- GET /status: 获取系统状态
- GET /health: 健康检查
"""

import os
import sys
import logging
import json
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from orchestrator import DevOpsDataOrchestrator

# 创建Flask应用
app = Flask(__name__)

# 全局变量
orchestrator = None
continuous_thread = None
stop_continuous = False


def setup_logging(log_config: dict):
    """
    设置日志配置
    
    Args:
        log_config (dict): 日志配置
    """
    # 创建日志目录
    log_file = log_config.get('file', 'logs/devops_data_generator.log')
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 设置日志格式
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    
    # 配置根日志器
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def init_orchestrator(config_dir=None):
    """
    初始化编排器
    
    Args:
        config_dir (str): 配置目录路径
        
    Returns:
        bool: 初始化是否成功
    """
    global orchestrator
    
    try:
        # 设置配置目录
        if config_dir is None:
            config_dir = os.path.join(project_root, 'config')
        
        # 初始化编排器
        orchestrator = DevOpsDataOrchestrator(config_dir)
        
        # 设置日志
        log_config = orchestrator.config_loader.get_logging_config()
        setup_logging(log_config)
        
        logger = logging.getLogger(__name__)
        logger.info("=== DevOps数据生成器初始化完成 ===")
        
        return True
    except Exception as e:
        print(f"初始化失败: {str(e)}")
        return False


def continuous_runner(interval):
    """
    持续运行的后台线程函数
    
    Args:
        interval (int): 执行间隔（秒）
    """
    global stop_continuous
    logger = logging.getLogger(__name__)
    
    while not stop_continuous:
        try:
            result = orchestrator.run_single_cycle_result()
            status = result.get('execution_summary', {}).get('status', 'error')
            if status == 'success':
                logger.info("持续运行 - 周期执行完成")
            elif status == 'partial_success':
                logger.warning("持续运行 - 周期部分成功")
            else:
                logger.error("持续运行 - 周期执行失败")
        except Exception as e:
            logger.error(f"持续运行出错: {str(e)}")
        
        # 等待间隔时间，或收到停止信号
        for _ in range(interval):
            if stop_continuous:
                break
            time.sleep(1)
    
    logger.info("持续运行模式已停止")


@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    """
    return jsonify({
        'status': 'healthy',
        'service': 'devops-data-generator',
        'timestamp': time.time()
    })


@app.route('/status', methods=['GET'])
def get_status():
    """
    获取系统状态
    """
    try:
        if orchestrator is None:
            return jsonify({
                'error': 'Orchestrator not initialized'
            }), 500
        
        status = orchestrator.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({
            'error': f'Failed to get status: {str(e)}'
        }), 500


@app.route('/invoke', methods=['POST'])
def invoke_task():
    """
    执行数据生成任务
    
    支持的参数：
    - mode: 'single' 或 'continuous'
    - interval: 持续模式的间隔时间（秒）
    - dry_run: 是否为测试运行
    """
    global continuous_thread, stop_continuous
    
    try:
        if orchestrator is None:
            return jsonify({
                'error': 'Orchestrator not initialized'
            }), 500
        
        # 获取请求参数 - 支持多种Content-Type
        data = {}
        content_type = request.content_type
        
        if content_type and 'application/json' in content_type:
            # 标准JSON请求
            data = request.get_json() or {}
        elif content_type and 'application/octet-stream' in content_type:
            # 处理octet-stream，尝试解析为JSON
            try:
                raw_data = request.get_data()
                if raw_data:
                    # 尝试解码为字符串并解析JSON
                    json_str = raw_data.decode('utf-8')
                    data = json.loads(json_str)
                else:
                    data = {}
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.error(f"解析octet-stream数据失败: {str(e)}")
                return jsonify({
                    'error': f'无法解析请求数据: {str(e)}',
                    'content_type': content_type
                }), 400
        elif request.form:
            # 表单数据
            data = request.form.to_dict()
            # 转换字符串值为合适的类型
            if 'interval' in data:
                try:
                    data['interval'] = int(data['interval'])
                except (ValueError, TypeError):
                    pass
            if 'dry_run' in data:
                data['dry_run'] = data['dry_run'].lower() in ('true', '1', 'yes')
        else:
            # 没有数据或未知格式，使用默认值
            data = {}
        
        mode = data.get('mode', 'single')
        interval = data.get('interval', 300)  # 默认5分钟
        dry_run = data.get('dry_run', False)
        
        logger = logging.getLogger(__name__)
        logger.info(f"收到invoke请求 - mode: {mode}, interval: {interval}, dry_run: {dry_run}")
        
        if dry_run:
            logger.info("运行在测试模式，不会发送数据到SLS")
        
        if mode == 'single':
            # 单次执行
            logger.info("执行单次数据生成周期")
            result = orchestrator.run_single_cycle_result()
            status = result.get('execution_summary', {}).get('status', 'error')

            if status == 'success':
                logger.info("单次执行完成")
                http_status = 200
                message = '单次执行完成'
            elif status == 'partial_success':
                logger.warning("单次执行部分成功")
                http_status = 200
                message = '单次执行部分成功'
            else:
                logger.error("单次执行失败")
                http_status = 500
                message = '单次执行失败'

            response_payload = {
                'status': status,
                'message': message,
                'mode': 'single'
            }
            response_payload.update(result)
            return jsonify(response_payload), http_status
                
        elif mode == 'continuous':
            # 持续运行模式
            if continuous_thread and continuous_thread.is_alive():
                return jsonify({
                    'status': 'error',
                    'message': '持续运行模式已在运行中'
                }), 400
            
            logger.info(f"启动持续运行模式，间隔: {interval}秒")
            stop_continuous = False
            continuous_thread = threading.Thread(
                target=continuous_runner, 
                args=(interval,),
                daemon=True
            )
            continuous_thread.start()
            
            return jsonify({
                'status': 'success',
                'message': f'持续运行模式已启动，间隔: {interval}秒',
                'mode': 'continuous',
                'interval': interval
            })
        
        else:
            return jsonify({
                'error': f'不支持的模式: {mode}，支持的模式: single, continuous'
            }), 400
            
    except Exception as e:
        logger.error(f"执行任务出错: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'执行任务出错: {str(e)}'
        }), 500


@app.route('/stop', methods=['POST'])
def stop_continuous_task():
    """
    停止持续运行任务
    """
    global stop_continuous, continuous_thread
    
    try:
        if not continuous_thread or not continuous_thread.is_alive():
            return jsonify({
                'status': 'warning',
                'message': '没有正在运行的持续任务'
            })
        
        logger = logging.getLogger(__name__)
        logger.info("收到停止持续运行的请求")
        
        stop_continuous = True
        continuous_thread.join(timeout=5)  # 等待最多5秒
        
        return jsonify({
            'status': 'success',
            'message': '持续运行任务已停止'
        })
        
    except Exception as e:
        logger.error(f"停止任务出错: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'停止任务出错: {str(e)}'
        }), 500


def main():
    """
    Flask应用启动函数
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="DevOps数据生成器Flask应用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                                  # 启动Flask服务，默认端口5000
  %(prog)s --port 8080                     # 指定端口启动
  %(prog)s --host 0.0.0.0 --port 8080     # 指定主机和端口启动
  %(prog)s --config /path/to/config       # 指定配置目录
  
启动后可通过以下API端点操作：
  POST /invoke    - 执行数据生成任务
  GET  /status    - 获取系统状态
  GET  /health    - 健康检查
  POST /stop      - 停止持续运行任务
        """
    )
    
    parser.add_argument(
        '--host', 
        type=str,
        default='127.0.0.1',
        help='Flask服务监听主机地址 (默认: 127.0.0.1)'
    )
    
    parser.add_argument(
        '--port', 
        type=int,
        default=5000,
        help='Flask服务监听端口 (默认: 5000)'
    )
    
    parser.add_argument(
        '--config', 
        type=str,
        help='配置文件目录路径（默认: ./config/）'
    )
    
    parser.add_argument(
        '--debug', 
        action='store_true',
        help='启用调试模式'
    )
    
    args = parser.parse_args()
    
    try:
        # 初始化编排器
        if not init_orchestrator(args.config):
            print("Failed to initialize orchestrator")
            sys.exit(1)
        
        logger = logging.getLogger(__name__)
        logger.info(f"=== DevOps数据生成器Flask应用启动 ===")
        logger.info(f"监听地址: {args.host}:{args.port}")
        logger.info(f"API端点:")
        logger.info(f"  POST /invoke    - 执行数据生成任务")
        logger.info(f"  GET  /status    - 获取系统状态")
        logger.info(f"  GET  /health    - 健康检查")
        logger.info(f"  POST /stop      - 停止持续运行任务")
        
        # 启动Flask应用
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
        global stop_continuous
        stop_continuous = True
        sys.exit(0)
    except Exception as e:
        print(f"程序启动失败: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
