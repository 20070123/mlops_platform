import os
import uuid

APP_ENV = os.getenv("APP_ENV", "dev")

from dotenv import load_dotenv

load_dotenv()
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

import docker
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Security, status
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app=FastAPI(title="MLOps 管理平台", 
    docs_url="/docs" if APP_ENV == "dev" else None,
    redoc_url="/redoc" if APP_ENV == "dev" else None
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
        content={"status": "error", "code": status_code, "message": message}
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc:StarletteHTTPException):
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


@app.get("/services")
def list_services(_: str = Depends(verify_ops_key)):
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        try:
            # 优先从容器自身配置中读取原始镜像名，避免因镜像被清退而报错
            image_tag = c.attrs.get("Config", {}).get("Image", "unknown")
        except Exception:
            # 如果引用的镜像已被删除，给个兜底值，不让接口崩掉
            image_tag = "unknown"

        result.append({
            "name": c.name,
            "status": c.status,
            "image": image_tag
        })
    return {"count": len(result), "services": result}

@app.post("/services/{name}/start")
@limiter.limit("5/minute")
def start_service(request: Request, name: str, x_client_id: str = Header(default="unknown"), _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.start()
        logger.info(f"容器 {name} 已启动 [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "started", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"启动容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

@app.post("/services/{name}/stop")
@limiter.limit("5/minute")
def stop_service(request: Request, name: str, x_client_id: str = Header(default="unknown"), _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.stop()
        logger.info(f"容器 {name} 已停止 [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "stopped", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"停止容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

@app.delete("/services/{name}")
@limiter.limit("5/minute")
def delete_service(request: Request, name: str, x_client_id: str = Header(default="unknown"), _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.remove(force=True)
        logger.info(f"容器 {name} 已删除 [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "removed", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"删除容器 {name} 失败： {e!s} [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

class DeployRequest(BaseModel):
    image: str
    host_port: int = 8000


@app.post("/services/{name}/deploy")
@limiter.limit("5/minute")
def deploy_service(request: Request, name: str, req: DeployRequest, x_client_id: str = Header(default="unknown"), _: str = Depends(verify_ops_key)):
    try:
        try:
            client.images.get(req.image)
        except docker.errors.ImageNotFound:
            logger.error(f"镜像不存在 [{request.state.request_id}]: {req.image}")
            return {"status": "error", "message": f"镜像 {req.image} 不存在"}

        try:
            old = client.containers.get(name)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

        client.containers.run(
            req.image,
            name=name,
            detach=True,
            ports={"8000/tcp": req.host_port}
        )
        logger.info(f"服务 {name} 已发布，镜像 {req.image} [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "deployed", "name": name, "image": req.image}
    except docker.errors.APIError as e:
        logger.info(f"发布服务 {name} 失败：{e!s} [{request.state.request_id}] 操作人:{x_client_id}")
        return {"status": "error", "message": "发布失败，请稍后重试"}