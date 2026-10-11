import os
import uuid
import requests

APP_ENV = os.getenv("APP_ENV", "dev")

from dotenv import load_dotenv

load_dotenv()
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

import docker
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
    title="MLOps 管理平台",
    docs_url="/docs" if APP_ENV == "dev" else None,
    redoc_url="/redoc" if APP_ENV == "dev" else None,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(f"收到请求 {request.method} {request.url.path} [{request_id}]")
    return response


def error_response(message: str, status_code: int = 400):
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "code": status_code, "message": message},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return error_response(exc.detail, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response("请求参数校验失败", 422)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕获的异常: {exc!s} [{request.state.request_id}]")
    return error_response("服务器内部错误，请稍后重试", 500)


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/")
def root():
    return {"message": "MLOps Platform is running"}


client = docker.from_env()
API_KEY = os.getenv("OPS_API_KEY")
if not API_KEY:
    raise RuntimeError("必须设置 OPS_API_KEY 环境变量（参考 .env.example）")

ops_key_header = APIKeyHeader(name="X-Ops-Key")


def verify_ops_key(api_key: str = Security(ops_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Ops Key")
    return api_key


@app.get("/v1/services")
def list_services(_: str = Depends(verify_ops_key)):
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        if c.name in ["ops-backend", "ops-frontend"]:
            continue
        try:
            # 优先从容器自身配置中读取原始镜像名，避免因镜像被清退而报错
            image_tag = c.attrs.get("Config", {}).get("Image", "unknown")
        except Exception: # noqa: BLE001
            # 如果引用的镜像已被删除，给个兜底值，不让接口崩掉
            image_tag = "unknown"

        result.append({
            "name": c.name,
            "status": c.status,
            "image": image_tag,
            "display_name": c.labels.get("mlops.display_name", ""),
            "input_count": c.labels.get("mlops.input_count", ""),
        })
    return {"count": len(result), "services": result}


@app.post("/v1/services/{name}/start")
@limiter.limit("5/minute")
def start_service(
    request: Request,
    name: str,
    x_client_id: str = Header(default="unknown"),
    _: str = Depends(verify_ops_key),
):
    try:
        container = client.containers.get(name)
        container.start()
        logger.info(
            f"容器 {name} 已启动 [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "started", "name": name}
    except docker.errors.APIError as e:
        logger.error(
            f"启动容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "error", "message": "操作失败，请稍后重试"}


@app.post("/v1/services/{name}/stop")
@limiter.limit("5/minute")
def stop_service(
    request: Request,
    name: str,
    x_client_id: str = Header(default="unknown"),
    _: str = Depends(verify_ops_key),
):
    try:
        container = client.containers.get(name)
        container.stop()
        logger.info(
            f"容器 {name} 已停止 [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "stopped", "name": name}
    except docker.errors.APIError as e:
        logger.error(
            f"停止容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "error", "message": "操作失败，请稍后重试"}


@app.delete("/v1/services/{name}")
@limiter.limit("5/minute")
def delete_service(
    request: Request,
    name: str,
    x_client_id: str = Header(default="unknown"),
    _: str = Depends(verify_ops_key),
):
    try:
        container = client.containers.get(name)
        container.remove(force=True)
        logger.info(
            f"容器 {name} 已删除 [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "removed", "name": name}
    except docker.errors.APIError as e:
        logger.error(
            f"删除容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "error", "message": "操作失败，请稍后重试"}


class DeployRequest(BaseModel):
    image: str
    host_port: int = 8000
    model_path: str = "../mlops_demo/models"
    display_name: str = "未命名模型"
    input_count: int = 0


@app.post("/v1/services/{name}/deploy")
@limiter.limit("5/minute")
def deploy_service(
    request: Request,
    name: str,
    req: DeployRequest,
    x_client_id: str = Header(default="unknown"),
    _: str = Depends(verify_ops_key),
):
    try:
        # 1. 检查镜像是否存在
        try:
            client.images.get(req.image)
        except docker.errors.ImageNotFound:
            logger.error(f"镜像不存在 [{request.state.request_id}]: {req.image}")
            return {"status": "error", "message": f"镜像 {req.image} 不存在"}

        # 2. 停掉旧容器，改名保留（用于回滚）
        old_container = None
        try:
            old_container = client.containers.get(name)
            old_container.stop()
            old_container.rename(f"{name}-backup")
            logger.info(f"旧容器 {name} 已停止并改名为 {name}-backup [{request.state.request_id}]")
        except docker.errors.NotFound:
            pass

        # 3. 启动新容器
        try:
            container = client.containers.run(
                req.image,
                name=name,
                detach=True,
                ports={"8000/tcp": req.host_port},
                volumes={req.model_path: {"bind": "/app/models", "mode": "ro"}},
                environment={
                    "DOCTOR_API_KEY": os.getenv("DOCTOR_API_KEY", "doctor_secret"),
                    "MODEL_VERSION": "v999",
                    "MODEL_PATH": "models/model.joblib",
                    "APP_ENV": "dev",
                },
                labels={
                    "mlops.type": "model-service",
                    "mlops.display_name": req.display_name,
                    "mlops.input_count": str(req.input_count),
                },
                network="mlops_platform_default",
            )
        except docker.errors.APIError as e:
            if old_container:
                old_container.rename(name)
                old_container.start()
            return {"status": "error", "message": f"启动新容器失败：{e!s}，已回滚到旧版本"}

        # 4. 部署自检
        import time
        base_url = f"http://{name}:8000"

        def rollback():
            container.remove(force=True)
            if old_container:
                old_container.rename(name)
                old_container.start()
                logger.info(f"已回滚到旧容器 {name} [{request.state.request_id}]")

        # 4.1 等待 /ready
        ready = False
        for _ in range(15):
            container.reload()
            if container.status != "running":
                rollback()
                return {"status": "error", "message": "自检失败：容器状态异常，已回滚到旧版本"}
            try:
                resp = requests.get(f"{base_url}/ready", timeout=3)
                if resp.status_code == 200:
                    ready = True
                    break
            except requests.RequestException:
                pass
            time.sleep(2)

        if not ready:
            rollback()
            return {"status": "error", "message": "自检失败：模型加载超时，已回滚到旧版本"}

        # 4.2 检查 /v1/schema
        try:
            schema_resp = requests.get(f"{base_url}/v1/schema", timeout=5)
            features = schema_resp.json().get("features", [])
            if not features:
                rollback()
                return {"status": "error", "message": "自检失败：schema.json 缺少 features，已回滚"}
        except requests.RequestException as e:
            rollback()
            return {"status": "error", "message": f"自检失败：schema 接口不可达，已回滚。{e!s}"}

        # 4.3 调 /v1/predict
        try:
            test_payload = {f["name"]: f.get("default", 0.0) for f in features}
            predict_resp = requests.post(
                f"{base_url}/v1/predict",
                json=test_payload,
                headers={"X-API-KEY": os.getenv("DOCTOR_API_KEY", "doctor_secret")},
                timeout=10,
            )
            if predict_resp.status_code != 200 or predict_resp.json().get("status") != "success":
                rollback()
                return {
                    "status": "error",
                    "message": f"自检失败：预测接口异常，已回滚。响应：{predict_resp.text[:200]}",
                }
        except requests.RequestException as e:
            rollback()
            return {"status": "error", "message": f"自检失败：预测接口不可达，已回滚。{e!s}"}

        # 5. 自检通过，删掉旧备份容器
        if old_container:
            old_container.remove(force=True)

        logger.info(
            f"服务 {name} 已发布，镜像 {req.image} [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "deployed", "name": name, "image": req.image}

    except docker.errors.APIError as e:
        logger.info(
            f"发布服务 {name} 失败：{e!s} [{request.state.request_id}] 操作人:{x_client_id}"
        )
        return {"status": "error", "message": "发布失败，请稍后重试"}