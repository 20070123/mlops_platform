# MLOps 模型服务管理平台

> 一个基于 FastAPI + Streamlit + Docker 构建的医疗模型推理与管理平台。支持动态特征表单、全链路追踪、自动化测试与 CI/CD 持续交付。

## 🏗️ 系统架构

本系统由 5 个 Docker 容器组成，使用 Docker Compose 统一编排。代码已按职责分离为 `ops/`（运维模块）与 `doctor/`（医生模块）两个独立包。

| 服务名称 | 容器名 | 宿主机端口 | 说明 |
| :--- | :--- | :--- | :--- |
| **inference** | medical-api | 8000 | 推理服务（FastAPI + Sklearn） |
| **ops-backend** | ops-backend | 9000 | 运维后端（提供容器管理 API） |
| **ops-frontend** | ops-frontend | 8501 | 运维前端（Streamlit 管理界面） |
| **doctor-backend** | doctor-backend | 9002 | 医生后端（转发预测请求） |
| **doctor-frontend** | doctor-frontend | 8502 | 医生前端（动态表单与预测结果） |

## ✨ 核心特性

1. **元数据驱动的动态表单**：前端根据 `schema.json` 自动生成输入框。新增特征时只需修改配置文件并重启推理服务，无需修改任何前端代码。
2. **全链路追踪**：基于 `X-Request-ID` 与 `X-Client-ID` 的日志追踪机制，支持从报错到后端日志的秒级定位。
3. **统一异常响应**：所有接口返回标准化 JSON 格式的错误信息，杜绝 HTML 报错导致前端崩溃。
4. **自动化测试与 CI/CD**：使用 Pytest 覆盖鉴权与核心业务逻辑，GitHub Actions 自动构建 4 个镜像并推送至 GHCR。

## 🔐 鉴权与安全

- 推理服务：`X-API-Key`
- 运维后端：`X-Ops-Key`
- 医生后端：`X-Doctor-Key`
- 所有服务均通过 `.env` 文件注入环境变量，**严禁将 `.env` 文件提交至 Git 仓库**。
- 生产环境自动隐藏 `/docs` 接口文档（通过 `APP_ENV=prod` 控制）。

## 🚀 快速启动

### 前置要求
- **本地开发环境**：安装 Docker Desktop (Windows / macOS)
- **生产服务器环境**：安装 Docker Engine (Linux) 及 Docker Compose 插件
- 确保 Docker 服务已正常启动

### 启动步骤

**1. 克隆代码仓库**
```bash
git clone https://github.com/20070123/mlops_platform.git
cd mlops_platform
```

**2. 准备环境变量文件（参考 .env.example）**
```bash
cp .env.example .env
```

**3. 一键启动所有服务**
```bash
docker compose up -d --build
```

**4. 查看服务状态**
```bash
docker compose ps
```

## 📦 医院内网离线部署指南
由于医院内网通常与互联网物理隔离，无法直接从 GitHub 拉取镜像。请按以下步骤离线部署：

**1. 在外部网络导出镜像：**
```bash
docker save -o mlops_platform.tar mlops_platform-doctor-backend mlops_platform-doctor-frontend mlops_platform-ops-backend mlops_platform-ops-frontend medical-rewrite:v4
```

**2. 将 mlops_platform.tar 文件拷贝至内网服务器。**

**3. 在内网服务器加载镜像并启动：**
```bash
docker load -i mlops_platform.tar
cd mlops_platform
docker compose up -d
```

## 🧪 自动化测试
本项目包含基于 Pytest 的自动化测试，覆盖健康检查、鉴权逻辑与业务列表 Mock 测试。
```bash
cd mlops_platform
python -m pytest tests/ -v
```

## 🌐 访问地址
运维管理平台：http://127.0.0.1:8501

医生预测平台：http://127.0.0.1:8502

推理服务 API 文档：http://127.0.0.1:8000/docs（生产环境自动隐藏）

## 🔄 CI/CD 自动化
本仓库已配置 GitHub Actions (.github/workflows/docker-build.yml)。
当向 main 分支推送代码时，会自动在云端构建以下 4 个 Docker 镜像并推送到 GitHub Container Registry (GHCR)：

ghcr.io/20070123/mlops_platform/doctor-backend

ghcr.io/20070123/mlops_platform/ops-backend

ghcr.io/20070123/mlops_platform/ops-frontend

ghcr.io/20070123/mlops_platform/doctor-frontend

## ⚠️ 免责声明
本系统预测结果仅供医疗参考，不作为诊断依据。最终诊断请以医生判断为准。