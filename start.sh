#!/bin/bash

# DesignKit 一键启动脚本

# 设置颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}       DesignKit 一键启动工具          ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""
echo -e "请选择启动模式:"
echo -e "  ${GREEN}1${NC}) 本地开发模式 (启动前端 Vite + 后端 FastAPI)"
echo -e "  ${GREEN}2${NC}) Docker 生产模式 (使用 docker-compose 启动全量服务)"
echo -e "  ${GREEN}3${NC}) 退出"
echo ""

read -p "请输入选项 [1-3]: " mode

case $mode in
  1)
    echo -e "\n${YELLOW}正在准备本地开发环境...${NC}"
    
    # 检查命令是否存在
    if ! command -v npm &> /dev/null; then
        echo "Error: 未找到 npm 命令，请先安装 Node.js"
        exit 1
    fi
    if ! command -v python3 &> /dev/null; then
        echo "Error: 未找到 python3 命令，请先安装 Python"
        exit 1
    fi

    # 启动后端
    echo -e "${GREEN}[1/2] 正在启动后端 FastAPI 服务...${NC}"
    cd server || exit
    
    # 如果没有虚拟环境，提示配置
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}检测到未配置 Python 虚拟环境，正在创建并安装依赖...${NC}"
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
    else
        source venv/bin/activate
    fi
    
    # 在后台运行后端
    uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!
    cd ..

    # 启动前端
    echo -e "${GREEN}[2/2] 正在启动前端 Vue 开发服务器...${NC}"
    cd web || exit
    
    # 如果没有 node_modules，安装依赖
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}检测到未安装前端依赖，正在安装...${NC}"
        npm install
    fi
    
    # 启动前端并保持在前台
    npm run dev
    
    # 当前端进程被终端（Ctrl+C）时，杀死后台的后端进程
    trap "kill $BACKEND_PID" EXIT
    ;;
    
  2)
    echo -e "\n${YELLOW}正在准备 Docker 生产环境...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo "Error: 未找到 docker 命令，请先安装 Docker"
        exit 1
    fi
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo "Error: 未找到 docker-compose 命令"
        exit 1
    fi

    echo -e "${GREEN}正在构建前端生产包...${NC}"
    cd web || exit
    npm install
    npm run build
    cd ..

    echo -e "${GREEN}正在启动 Docker 容器...${NC}"
    # 兼容老版本 docker-compose 和新版本 docker compose
    if command -v docker-compose &> /dev/null; then
        docker-compose up --build -d
    else
        docker compose up --build -d
    fi
    
    echo -e "\n${GREEN}✅ 服务已在后台启动！${NC}"
    echo -e "访问应用: http://localhost"
    echo -e "访问 API Docs: http://localhost/api/docs"
    echo -e "\n使用 'docker-compose logs -f' 查看运行日志。"
    echo -e "使用 'docker-compose down' 停止服务。"
    ;;
    
  3)
    echo "已退出。"
    exit 0
    ;;
    
  *)
    echo "无效的选择，请输入 1, 2 或 3。"
    exit 1
    ;;
esac
