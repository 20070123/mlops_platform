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
import requests
from fastapi import FastAPI, Header, Request, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app=FastAPI(title="医生端后端", 
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
    logger.error(f"未捕获的异常: {exc!s} [{request.state.request_id}] 客户端:{x_client_id}")
    return error_response("服务器内部错误，请稍后重试", 500)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

client = docker.from_env()
API_KEY = os.getenv("DOCTOR_API_KEY")
if not API_KEY:
    raise RuntimeError("必须设置 DOCTOR_API_KEY 环境变量（参考 .env.example）")

doctor_key_header = APIKeyHeader(name="X-Doctor-Key")

def verify_doctor_key(api_key: str = Security(doctor_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Doctor Key")
    return api_key

DOCKER_HOST_IP = os.getenv("DOCKER_HOST_IP", "127.0.0.1")

@app.get("/")
def root():
    return {"message": "Doctor Backend is running"}

@app.get("/v1/models")
def list_models(_: str = Depends(verify_doctor_key)):
    containers = client.containers.list(filters={"status": "running"})
    result = []
    for c in containers:
        if c.name.startswith("medical"):
            result.append(c.name)
    return {"models": result}

@app.post("/v1/predict/{model_name}")
@limiter.limit("10/minute")
def doctor_predict(request: Request,
                   model_name: str,
                   body: dict,
                   x_client_id: str = Header(default="unknown"),
                   _: str = Depends(verify_doctor_key)
    ):
    try:
        container = client.containers.get(model_name)
        if container.status != "running":
            logger.warning(f"模型当前不可用 [{request.state.request_id}]: {model_name} 客户端:{x_client_id}")
            return {"status": "error", "message": "该模型当前不可用"}

        ports = container.attrs["NetworkSettings"]["Ports"]
        host_port = ports["8000/tcp"][0]["HostPort"]

        target_url = f"http://{DOCKER_HOST_IP}:{host_port}/predict"
        headers = {"X-API-KEY": API_KEY,
                   "X-Client-ID": x_client_id
        }
        response = requests.post(target_url, json=body, headers=headers, timeout=10)

        logger.info(f"预测请求成功 [{request.state.request_id}] 客户端:{x_client_id}")
        return response.json()
    except docker.errors.NotFound:
        logger.error(f"模型不存在 [{request.state.request_id}]: {model_name} 客户端:{x_client_id}")
        return {"status": "error", "message": f"模型{model_name}不存在"}
    except (docker.errors.APIError, requests.RequestException) as e:
        logger.error(f"转发预测请求失败 [{request.state.request_id}]: {e!s} 客户端:{x_client_id}")
        return {"status": "error", "message": "预测失败，请稍后重试"}