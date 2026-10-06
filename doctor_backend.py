import os

from dotenv import load_dotenv

load_dotenv()
import logging

import docker
import requests
from fastapi import FastAPI, Header, Request, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app = FastAPI(title="医生端后端")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

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

@app.get("/models")
def list_models():
    containers = client.containers.list(filters={"status": "running"})
    result = []
    for c in containers:
        if c.name.startswith("medical"):
            result.append(c.name)
    return {"models": result}

@app.post("/predict/{model_name}")
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
            return {"status": "error", "message": "该模型当前不可用"}

        ports = container.attrs["NetworkSettings"]["Ports"]
        host_port = ports["8000/tcp"][0]["HostPort"]

        target_url = f"http://{DOCKER_HOST_IP}:{host_port}/predict"
        headers = {"X-API-KEY": API_KEY,
                   "X-Client-ID": x_client_id
        }
        response = requests.post(target_url, json=body, headers=headers, timeout=10)

        return response.json()
    except docker.errors.NotFound:
        return {"status": "error", "message": f"模型{model_name}不存在"}
    except (docker.errors.APIError, requests.RequestException) as e:
        logger.error(f"转发预测请求失败: {e!s}")
        return {"status": "error", "message": "预测失败，请稍后重试"}