#!/bin/bash

# DevOps数据生成器 Docker运行脚本
# 提供多种运行模式和配置选项

set -e

# 脚本参数
IMAGE_NAME="devops-data-generator:latest"
CONTAINER_NAME="devops-data-generator"
RUN_MODE="single"
INTERVAL=""
CONFIG_FILE=""
LOG_LEVEL=""
DETACH=""
INTERACTIVE=""
REMOVE_ON_EXIT="--rm"
EXTRA_ARGS=""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 显示帮助信息
show_help() {
    cat << EOF
DevOps数据生成器 Docker运行脚本

使用方法:
    $0 [选项]

选项:
    -i, --image IMAGE       指定要运行的镜像 (默认: devops-data-generator:latest)
    -n, --name NAME         指定容器名称 (默认: devops-data-generator)
    -m, --mode MODE         运行模式: single|continuous (默认: single)
    -t, --interval SEC      持续模式的执行间隔(秒) (默认: 300)
    -c, --config FILE       配置文件路径 (默认: ./config/app_config.yaml)
    -l, --log-level LEVEL   日志级别: DEBUG|INFO|WARNING|ERROR (默认: INFO)
    -d, --detach            后台运行
    --interactive           交互模式运行
    --no-remove             容器退出后不自动删除
    --dry-run               测试运行，不发送数据到SLS
    --status                显示系统状态
    --shell                 进入容器shell
    -h, --help              显示此帮助信息

示例:
    $0                                          # 默认单次执行
    $0 -m continuous -t 600 -d                # 后台持续运行，10分钟间隔
    $0 -c /path/to/config.yaml -l DEBUG       # 指定配置文件和日志级别
    $0 --status                                # 查看系统状态
    $0 --shell                                 # 进入容器调试
    $0 --dry-run                              # 测试运行
    $0 --interactive                          # 交互模式

EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -n|--name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        -m|--mode)
            RUN_MODE="$2"
            shift 2
            ;;
        -t|--interval)
            INTERVAL="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -l|--log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -d|--detach)
            DETACH="-d"
            REMOVE_ON_EXIT=""
            shift
            ;;
        --interactive)
            INTERACTIVE="-it"
            shift
            ;;
        --no-remove)
            REMOVE_ON_EXIT=""
            shift
            ;;
        --dry-run)
            EXTRA_ARGS="$EXTRA_ARGS --dry-run"
            shift
            ;;
        --status)
            EXTRA_ARGS="$EXTRA_ARGS --status"
            shift
            ;;
        --shell)
            INTERACTIVE="-it"
            EXTRA_ARGS="bash"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_message $RED "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 检查Docker是否可用
if ! command -v docker &> /dev/null; then
    print_message $RED "错误: Docker未安装或不可用"
    exit 1
fi

# 检查镜像是否存在
if ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
    print_message $RED "错误: 镜像 $IMAGE_NAME 不存在"
    print_message $YELLOW "请先构建镜像: ./scripts/docker-build.sh"
    exit 1
fi

# 设置默认配置文件路径
if [ -z "$CONFIG_FILE" ]; then
    CONFIG_FILE="./config/app_config.yaml"
fi

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    print_message $RED "错误: 配置文件 $CONFIG_FILE 不存在"
    print_message $YELLOW "请复制并配置: cp config/app_config.yaml.sample config/app_config.yaml"
    exit 1
fi

# 创建日志目录
mkdir -p ./logs

# 构建Docker运行命令
DOCKER_CMD="docker run"

# 基本选项
if [ -n "$REMOVE_ON_EXIT" ]; then
    DOCKER_CMD="$DOCKER_CMD $REMOVE_ON_EXIT"
fi

if [ -n "$DETACH" ]; then
    DOCKER_CMD="$DOCKER_CMD $DETACH"
fi

if [ -n "$INTERACTIVE" ]; then
    DOCKER_CMD="$DOCKER_CMD $INTERACTIVE"
fi

# 容器名称（仅在非临时运行时使用）
if [ -z "$REMOVE_ON_EXIT" ]; then
    DOCKER_CMD="$DOCKER_CMD --name $CONTAINER_NAME"
fi

# 环境变量
if [ -n "$LOG_LEVEL" ]; then
    DOCKER_CMD="$DOCKER_CMD -e LOG_LEVEL=$LOG_LEVEL"
fi

# 卷挂载
DOCKER_CMD="$DOCKER_CMD -v $(realpath "$CONFIG_FILE"):/app/config/app_config.yaml:ro"
DOCKER_CMD="$DOCKER_CMD -v $(pwd)/logs:/app/logs"

# 如果存在其他配置文件，也挂载进去
for config in "data_mapping.yaml" "manage_mapping.yaml" "static_topo.yaml" "repo_image_mapping.yaml"; do
    if [ -f "./config/$config" ]; then
        DOCKER_CMD="$DOCKER_CMD -v $(pwd)/config/$config:/app/config/$config:ro"
    fi
done

# 镜像名称
DOCKER_CMD="$DOCKER_CMD $IMAGE_NAME"

# 应用程序参数
if [ "$EXTRA_ARGS" = "bash" ]; then
    # Shell模式
    DOCKER_CMD="$DOCKER_CMD bash"
elif [ -n "$EXTRA_ARGS" ]; then
    # 带额外参数
    DOCKER_CMD="$DOCKER_CMD python main.py $EXTRA_ARGS"
else
    # 正常运行模式
    APP_ARGS="--mode $RUN_MODE"
    
    if [ "$RUN_MODE" = "continuous" ] && [ -n "$INTERVAL" ]; then
        APP_ARGS="$APP_ARGS --interval $INTERVAL"
    fi
    
    DOCKER_CMD="$DOCKER_CMD python main.py $APP_ARGS"
fi

print_message $BLUE "启动DevOps数据生成器..."
print_message $BLUE "镜像: $IMAGE_NAME"
print_message $BLUE "模式: $RUN_MODE"
print_message $BLUE "配置文件: $CONFIG_FILE"

if [ -n "$DETACH" ]; then
    print_message $YELLOW "容器将在后台运行..."
else
    print_message $YELLOW "容器将在前台运行，按 Ctrl+C 停止..."
fi

# 显示完整的Docker命令（调试用）
if [ -n "$DEBUG" ]; then
    print_message $BLUE "执行命令: $DOCKER_CMD"
fi

# 执行Docker命令
eval $DOCKER_CMD

# 如果是后台运行，提供一些有用的命令
if [ -n "$DETACH" ]; then
    print_message $GREEN "✅ 容器已启动"
    print_message $BLUE "有用的命令:"
    echo ""
    echo "# 查看容器状态："
    echo "docker ps"
    echo ""
    echo "# 查看日志："
    echo "docker logs -f $CONTAINER_NAME"
    echo ""
    echo "# 进入容器："
    echo "docker exec -it $CONTAINER_NAME bash"
    echo ""
    echo "# 停止容器："
    echo "docker stop $CONTAINER_NAME"
    echo ""
    echo "# 删除容器："
    echo "docker rm $CONTAINER_NAME"
fi
