import os

from dotenv import load_dotenv

load_dotenv()
import logging

import docker
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app = FastAPI(title="MLOps 管理平台")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

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
def list_services():
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        try:
            # 尝试获取镜像标签
            image_tag = c.image.tags[0] if c.image.tags else "unknown"
        except docker.errors.ImageNotFound:
            # 如果引用的镜像已被删除，给个兜底值，不让接口崩掉
            image_tag = "unknown (image not found)"

        result.append({
            "name": c.name,
            "status": c.status,
            "image": image_tag
        })
    return {"count": len(result), "services": result}

@app.post("/services/{name}/start")
@limiter.limit("5/minute")
def start_service(request: Request, name: str, _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.start()
        logger.info(f"容器 {name} 已启动")
        return {"status": "started", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"启动容器 {name} 失败： {e!s}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

@app.post("/services/{name}/stop")
@limiter.limit("5/minute")
def stop_service(request: Request, name: str, _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.stop()
        logger.info(f"容器 {name} 已停止")
        return {"status": "stopped", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"停止容器 {name} 失败： {e!s}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

@app.delete("/services/{name}")
@limiter.limit("5/minute")
def delete_service(request: Request, name: str, _: str = Depends(verify_ops_key)):
    try:
        container = client.containers.get(name)
        container.remove(force=True)
        logger.info(f"容器 {name} 已删除")
        return {"status": "removed", "name": name}
    except docker.errors.APIError as e:
        logger.error(f"删除容器 {name} 失败： {e!s}")
        return {"status": "error", "message": "操作失败，请稍后重试"}

class DeployRequest(BaseModel):
    image: str
    host_port: int = 8000


@app.post("/services/{name}/deploy")
@limiter.limit("5/minute")
def deploy_service(request: Request, name: str, req: DeployRequest, _: str = Depends(verify_ops_key)):
    try:
        try:
            client.images.get(req.image)
        except docker.errors.ImageNotFound:
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
        logger.info(f"服务 {name} 已发布，镜像 {req.image}")
        return {"status": "deployed", "name": name, "image": req.image}
    except docker.errors.APIError as e:
        logger.info(f"发布服务 {name} 失败：{e!s}")
        return {"status": "error", "message": "发布失败，请稍后重试"}