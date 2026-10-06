# MLOps 模型服务管理平台

> 一个完整的 MLOps 推理服务及管理平台，包含推理后端、运维管理端和医生预测端。实现了 Docker 容器化、Docker Compose 编排以及 GitHub Actions 自动化 CI/CD 构建。

## 🏗️ 系统架构

本系统由 5 个 Docker 容器组成，使用 Docker Compose 统一编排：

| 服务名称 | 容器名 | 宿主机端口 | 说明 |
| :--- | :--- | :--- | :--- |
| **inference** | medical-api | 8000 | 模型推理服务（已训练好的 sklearn 模型） |
| **ops-backend** | ops-backend | 9000 | 运维管理后端，负责操作 Docker 容器 |
| **ops-frontend** | ops-frontend | 8501 | 运维管理前端（Streamlit） |
| **doctor-backend** | doctor-backend | 9002 | 医生预测后端，负责转发预测请求 |
| **doctor-frontend** | doctor-frontend | 8502 | 医生预测前端（Streamlit） |

## 🔐 鉴权与安全

- 推理服务：`X-API-Key`
- 运维后端：`X-Ops-Key`
- 医生后端：`X-Doctor-Key`
- 所有服务均通过 `.env` 文件注入环境变量，**严禁将 `.env` 文件提交至 Git 仓库**。

## 🚀 快速启动

### 前置要求
- **本地开发环境**：安装 Docker Desktop (Windows / macOS)
- **生产服务器环境**：安装 Docker Engine (Linux) 及 Docker Compose 插件
- 确保 Docker 服务已正常启动

### 启动步骤
1. 克隆代码仓库：
   ```bash
   git clone https://github.com/20070123/mlops_platform.git
   cd mlops_platform
准备环境变量文件（参考 .env.example）：

bash
cp .env.example .env
# 编辑 .env 文件，填入真实的 API 密钥
一键启动所有服务：

bash
docker compose up -d --build
查看服务状态：

bash
docker compose ps
🌐 访问地址
运维管理平台：http://127.0.0.1:8501

医生预测平台：http://127.0.0.1:8502

推理服务 API 交互式文档（Swagger UI）：http://127.0.0.1:8000/docs

🔄 CI/CD 自动化
本仓库已配置 GitHub Actions (.github/workflows/docker-build.yml)。
当向 main 分支推送代码时，会自动在云端构建以下 4 个 Docker 镜像并推送到 GitHub Container Registry (GHCR)：

ghcr.io/20070123/mlops_platform/doctor-backend

ghcr.io/20070123/mlops_platform/ops-backend

ghcr.io/20070123/mlops_platform/ops-frontend

ghcr.io/20070123/mlops_platform/doctor-frontend

⚠️ 免责声明
本系统预测结果仅供医疗参考，不作为诊断依据。最终诊断请以医生判断为准。