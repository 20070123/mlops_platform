import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:9000")

STATUS_MAP = {
    "running": "🟢 运行中",
    "exited": "🔴 已停止",
    "created": "⚪ 已创建",
    "paused": "🟡 已暂停",
    "restarting": "🔄 重启中",
}

st.title("MLOps 模型服务管理平台")

if "deploy_target" not in st.session_state:
    st.session_state.deploy_target = None
try:
    response = requests.get(f"{BACKEND_URL}/services", timeout=10)
    data = response.json()
except (requests.ConnectionError, requests.Timeout):
    st.error("⚠️ 无法连接到运维后端，请稍后重试。")
    st.stop()

st.write(f"当前共有 {data['count']} 个服务")

h1, h2, h3, h4, h5, h6, h7 = st.columns([3, 2, 3, 2, 2, 2, 2])
with h1:
    st.write("**服务名**")
with h2:
    st.write("**状态**")
with h3:
    st.write("**镜像**")
with h4:
    st.write("**操作**")

for svc in data["services"]:
    col1, col2, col3, col4, col5, col6, col7 = st.columns([3,2,3,2,2,2,2])
    with col1:
        st.write(svc["name"])
    with col2:
        status_cn = STATUS_MAP.get(svc["status"], svc["status"])
        st.write(status_cn)
    with col3:
        st.write(svc["image"])
    with col4:
        if st.button("启动", key=f"start_{svc["name"]}"):
            requests.post(f"{BACKEND_URL}/services/{svc['name']}/start")
            st.rerun()
    with col5:
        if st.button("停止", key=f"stop_{svc["name"]}"):
            requests.post(f"{BACKEND_URL}/services/{svc['name']}/stop")
            st.rerun()
    with col6:
        if st.button("删除", key=f"remove_{svc["name"]}"):
            requests.delete(f"{BACKEND_URL}/services/{svc['name']}")
            st.rerun()
    with col7:
        if st.button("发布", key=f"deploy_{svc['name']}"):
            st.session_state.deploy_target = svc["name"]
            st.rerun()

st.divider()
st.subheader("新建服务")

new_name = st.text_input("服务名称", value="medical-api-2")
new_image = st.text_input("镜像名称", value="medical-rewrite:v1")
new_port = st.number_input("宿主机端口", value=8001, step=1)

if st.button("创建服务", key="create_service"):
    requests.post(
        f"{BACKEND_URL}/services/{new_name}/deploy",
        json={"image": new_image, "host_port": new_port}
    )
    st.rerun()

@st.dialog("发布新版本")
def deploy_dialog():
    st.write(f"服务: {st.session_state.deploy_target}")
    deploy_image = st.text_input("新镜像名", value="medical-rewrite:v1")
    deploy_port = st.number_input("宿主机端口", value=8000, step=1)
    
    if st.button("确认发布", key="confirm_deploy"):
        requests.post(
            f"{BACKEND_URL}/services/{st.session_state.deploy_target}/deploy",
            json={"image": deploy_image, "host_port": int(deploy_port)}
        )
        st.session_state.deploy_target = None
        st.rerun()

if st.session_state.deploy_target:
    deploy_dialog()