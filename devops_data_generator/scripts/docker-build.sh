#!/bin/bash

# DevOps数据生成器 Docker镜像构建脚本
# 提供多种构建选项和优化功能

set -e

# 脚本参数
IMAGE_NAME="devops-data-generator"
IMAGE_TAG="latest"
BUILD_ARGS=""
NO_CACHE=""
VERBOSE=""
PUSH_IMAGE=""
REGISTRY=""

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
DevOps数据生成器 Docker构建脚本

使用方法:
    $0 [选项]

选项:
    -t, --tag TAG           指定镜像标签 (默认: latest)
    -n, --name NAME         指定镜像名称 (默认: devops-data-generator)
    -r, --registry URL      指定镜像仓库地址
    -p, --push              构建后推送到镜像仓库
    --no-cache              不使用构建缓存
    --verbose               显示详细构建信息
    -h, --help              显示此帮助信息

示例:
    $0                                      # 默认构建
    $0 -t v1.0.0                          # 指定标签
    $0 -n my-generator -t dev              # 指定名称和标签
    $0 -r registry.example.com -p         # 构建并推送
    $0 --no-cache --verbose               # 无缓存详细构建

EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH_IMAGE="true"
            shift
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --verbose)
            VERBOSE="--progress=plain"
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

# 构建完整的镜像名称
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
fi

# 检查Docker是否可用
if ! command -v lima &> /dev/null && ! command -v docker &> /dev/null; then
    print_message $RED "错误: Docker或Lima未安装或不可用"
    exit 1
fi

# 选择使用的容器工具
if command -v lima &> /dev/null; then
    DOCKER_CMD="lima nerdctl"
    PLATFORM_ARG="--platform=linux/amd64"
    print_message $BLUE "使用Lima + nerdctl进行构建"
else
    DOCKER_CMD="docker"
    PLATFORM_ARG="--platform=linux/amd64"
    print_message $BLUE "使用Docker进行构建"
fi

# 检查Dockerfile是否存在
if [ ! -f "Dockerfile" ]; then
    print_message $RED "错误: 当前目录中未找到Dockerfile"
    exit 1
fi

print_message $BLUE "开始构建Docker镜像..."
print_message $BLUE "镜像名称: $FULL_IMAGE_NAME"
print_message $BLUE "构建选项: $NO_CACHE $VERBOSE"

# 记录构建开始时间
start_time=$(date +%s)

# 执行Docker构建
print_message $YELLOW "正在构建镜像..."
if $DOCKER_CMD build \
    $NO_CACHE \
    $VERBOSE \
    $PLATFORM_ARG \
    -t "$FULL_IMAGE_NAME" \
    $BUILD_ARGS \
    .; then
    
    # 计算构建时间
    end_time=$(date +%s)
    build_time=$((end_time - start_time))
    
    print_message $GREEN "✅ 镜像构建成功!"
    print_message $GREEN "构建时间: ${build_time}秒"
    
    # 显示镜像信息
    print_message $BLUE "镜像信息:"
    $DOCKER_CMD images "$FULL_IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" || $DOCKER_CMD images "$FULL_IMAGE_NAME"
    
    # 如果指定了推送选项
    if [ "$PUSH_IMAGE" = "true" ]; then
        if [ -z "$REGISTRY" ]; then
            print_message $YELLOW "⚠️  未指定镜像仓库，跳过推送"
        else
            print_message $YELLOW "正在推送镜像到仓库..."
            if $DOCKER_CMD push "$FULL_IMAGE_NAME"; then
                print_message $GREEN "✅ 镜像推送成功!"
            else
                print_message $RED "❌ 镜像推送失败!"
                exit 1
            fi
        fi
    fi
    
    # 提供运行建议
    print_message $BLUE "运行建议:"
    echo ""
    echo "# Flask应用运行（推荐）："
    echo "docker run -d --name devops-generator -p 5000:5000 $FULL_IMAGE_NAME"
    echo ""
    echo "# 挂载配置目录运行："
    echo "docker run -d --name devops-generator -p 5000:5000 -v \$(pwd)/config:/app/config $FULL_IMAGE_NAME"
    echo ""
    echo "# 测试健康检查："
    echo "curl http://localhost:5000/health"
    echo "# 或使用Python（如果curl不可用）："
    echo "python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:5000/health').read().decode())\""
    echo ""
    echo "# 执行单次任务："
    echo "curl -X POST http://localhost:5000/invoke -H 'Content-Type: application/json' -d '{\"mode\": \"single\"}'"
    echo ""
    echo "# 使用Docker Compose运行："
    echo "docker-compose up -d"
    
else
    print_message $RED "❌ 镜像构建失败!"
    exit 1
fi

# 清理构建缓存（可选）
if [ "$NO_CACHE" ]; then
    print_message $YELLOW "正在清理Docker构建缓存..."
    lima nerdctl  builder prune -f
fi

print_message $GREEN "构建脚本执行完成!"
