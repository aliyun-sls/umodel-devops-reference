#!/bin/bash

# DevOps数据生成器 快速启动脚本
# 一键完成环境准备、镜像构建和容器运行

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 脚本参数
SKIP_BUILD=""
SKIP_CONFIG=""
RUN_MODE="single"
FORCE=""

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# 打印标题
print_title() {
    echo ""
    echo -e "${CYAN}================================${NC}"
    echo -e "${CYAN} DevOps数据生成器 快速启动${NC}"
    echo -e "${CYAN}================================${NC}"
    echo ""
}

# 显示帮助信息
show_help() {
    cat << EOF
DevOps数据生成器 快速启动脚本

使用方法:
    $0 [选项]

选项:
    --skip-build        跳过镜像构建步骤
    --skip-config       跳过配置文件检查和创建
    -m, --mode MODE     运行模式: single|continuous (默认: single)
    -f, --force         强制覆盖现有配置文件
    -h, --help          显示此帮助信息

示例:
    $0                          # 完整的快速启动流程
    $0 --skip-build             # 跳过构建，直接运行
    $0 -m continuous            # 持续运行模式
    $0 -f                       # 强制重新创建配置文件

EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD="true"
            shift
            ;;
        --skip-config)
            SKIP_CONFIG="true"
            shift
            ;;
        -m|--mode)
            RUN_MODE="$2"
            shift 2
            ;;
        -f|--force)
            FORCE="true"
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

# 检查必要工具
check_prerequisites() {
    print_message $BLUE "检查前置条件..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        print_message $RED "❌ Docker未安装"
        print_message $YELLOW "请安装Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # 检查Docker是否运行
    if ! docker info &> /dev/null; then
        print_message $RED "❌ Docker未运行"
        print_message $YELLOW "请启动Docker服务"
        exit 1
    fi
    
    print_message $GREEN "✅ Docker检查通过"
    
    # 检查Docker Compose
    if command -v docker-compose &> /dev/null; then
        print_message $GREEN "✅ Docker Compose可用"
    else
        print_message $YELLOW "⚠️  Docker Compose未安装，将使用普通Docker命令"
    fi
}

# 准备配置文件
prepare_config() {
    if [ "$SKIP_CONFIG" = "true" ]; then
        print_message $YELLOW "跳过配置文件准备"
        return 0
    fi
    
    print_message $BLUE "准备配置文件..."
    
    # 创建config目录
    mkdir -p config
    
    # 检查主配置文件
    if [ ! -f "config/app_config.yaml" ] || [ "$FORCE" = "true" ]; then
        if [ -f "config/app_config.yaml.sample" ]; then
            print_message $YELLOW "创建配置文件: config/app_config.yaml"
            cp config/app_config.yaml.sample config/app_config.yaml
            print_message $CYAN "📝 请编辑 config/app_config.yaml 文件，填入您的阿里云访问凭证："
            echo ""
            echo "  vim config/app_config.yaml"
            echo ""
            echo "需要配置的主要信息："
            echo "  - aliyun.access_key_id: 您的AccessKey ID"
            echo "  - aliyun.access_key_secret: 您的AccessKey Secret"
            echo "  - devops.organization_id: DevOps组织ID"
            echo "  - sls.project: SLS项目名称"
            echo ""
            read -p "配置完成后按Enter继续..." -r
        else
            print_message $RED "❌ 未找到配置文件模板: config/app_config.yaml.sample"
            exit 1
        fi
    else
        print_message $GREEN "✅ 配置文件已存在"
    fi
    
    # 验证配置文件
    if [ -f "config/app_config.yaml" ]; then
        # 简单验证配置文件不为空且包含必要字段
        if grep -q "access_key_id:" config/app_config.yaml && \
           grep -q "access_key_secret:" config/app_config.yaml; then
            print_message $GREEN "✅ 配置文件验证通过"
        else
            print_message $YELLOW "⚠️  配置文件可能不完整，请检查必要的凭证信息"
        fi
    fi
    
    # 创建日志目录
    mkdir -p logs
    print_message $GREEN "✅ 日志目录已创建"
}

# 构建Docker镜像
build_image() {
    if [ "$SKIP_BUILD" = "true" ]; then
        print_message $YELLOW "跳过镜像构建"
        return 0
    fi
    
    print_message $BLUE "构建Docker镜像..."
    
    # 检查是否存在构建脚本
    if [ -f "scripts/docker-build.sh" ]; then
        print_message $CYAN "使用构建脚本..."
        ./scripts/docker-build.sh
    else
        print_message $CYAN "使用Docker命令直接构建..."
        docker build -t devops-data-generator:latest .
    fi
    
    print_message $GREEN "✅ 镜像构建完成"
}

# 运行容器
run_container() {
    print_message $BLUE "启动容器..."
    
    # 检查是否存在运行脚本
    if [ -f "scripts/docker-run.sh" ]; then
        print_message $CYAN "使用运行脚本启动容器..."
        if [ "$RUN_MODE" = "continuous" ]; then
            ./scripts/docker-run.sh -m continuous -d
            print_message $GREEN "✅ 容器已在后台持续运行"
            print_message $BLUE "查看日志: docker logs -f devops-data-generator"
        else
            ./scripts/docker-run.sh -m single
        fi
    else
        print_message $CYAN "使用Docker命令直接运行..."
        if [ "$RUN_MODE" = "continuous" ]; then
            docker run -d \
                --name devops-data-generator \
                --restart unless-stopped \
                -v $(pwd)/config/app_config.yaml:/app/config/app_config.yaml:ro \
                -v $(pwd)/logs:/app/logs \
                devops-data-generator:latest \
                python main.py --mode continuous --interval 300
            print_message $GREEN "✅ 容器已在后台持续运行"
        else
            docker run --rm \
                -v $(pwd)/config/app_config.yaml:/app/config/app_config.yaml:ro \
                -v $(pwd)/logs:/app/logs \
                devops-data-generator:latest
        fi
    fi
}

# 显示后续操作建议
show_next_steps() {
    print_message $GREEN "🎉 快速启动完成！"
    echo ""
    print_message $CYAN "后续操作建议："
    echo ""
    
    if [ "$RUN_MODE" = "continuous" ]; then
        echo "📊 监控和管理："
        echo "  docker logs -f devops-data-generator    # 查看实时日志"
        echo "  docker stats devops-data-generator       # 查看资源使用"
        echo "  docker stop devops-data-generator        # 停止服务"
        echo "  docker start devops-data-generator       # 启动服务"
        echo ""
        echo "📁 日志文件位置："
        echo "  ./logs/devops_data_generator.log"
    else
        echo "🔄 再次运行："
        echo "  ./scripts/docker-run.sh                  # 单次执行"
        echo "  ./scripts/docker-run.sh -m continuous -d # 后台持续运行"
        echo ""
        echo "🛠️  其他操作："
        echo "  ./scripts/docker-run.sh --status         # 查看系统状态"
        echo "  ./scripts/docker-run.sh --dry-run        # 测试运行"
        echo "  ./scripts/docker-run.sh --shell          # 进入容器调试"
    fi
    
    echo ""
    echo "📚 更多信息："
    echo "  cat DOCKER_GUIDE.md                      # 详细使用指南"
    echo "  cat README.md                            # 项目文档"
    echo ""
}

# 错误处理
error_handler() {
    print_message $RED "❌ 脚本执行失败！"
    print_message $YELLOW "请检查错误信息并重试"
    print_message $BLUE "如需帮助，请查看 DOCKER_GUIDE.md 或联系技术支持"
    exit 1
}

# 设置错误处理
trap 'error_handler' ERR

# 主执行流程
main() {
    print_title
    
    # 步骤1: 检查前置条件
    check_prerequisites
    
    # 步骤2: 准备配置文件
    prepare_config
    
    # 步骤3: 构建镜像
    build_image
    
    # 步骤4: 运行容器
    run_container
    
    # 步骤5: 显示后续步骤
    show_next_steps
}

# 运行主函数
main "$@"
