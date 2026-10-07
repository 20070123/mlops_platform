import os
import uuid

import requests
import streamlit as st

DOCTOR_BACKEND_URL = os.getenv("DOCTOR_BACKEND_URL", "http://127.0.0.1:9002")
DOCTOR_KEY = os.getenv("DOCTOR_API_KEY", "doctor_secret")

st.set_page_config(page_title="医生端预测", layout="wide")
st.title("医疗模型预测平台")

try:
    response = requests.get(
        f"{DOCTOR_BACKEND_URL}/models",
        headers={
            "X-Doctor-Key": DOCTOR_KEY,
        },
        timeout=10
    )
    if response.status_code != 200:
        st.error(f"加载模型列表失败: {response.json().get('message', '未知错误')}")
        st.stop()
    models = response.json()["models"]
except (requests.ConnectionError, requests.Timeout):
    st.error("无法连接到模型服务，请稍后重试。")
    st.stop()

selected_model = st.selectbox("选择模型", models)

st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    age = st.number_input("年龄", value=60, min_value=0, max_value=120)
with col2:
    heart_rate = st.number_input("心率", value=85, min_value=20, max_value=250)
with col3:
    spo2 = st.number_input("血氧",value=95, min_value=0, max_value=100)

if st.button("预测"):
    if not selected_model:
        st.error("请先选择有效模型")
        st.stop()
    
    req_id = str(uuid.uuid4())

    payload = {
        "age": int(age),
        "heart_rate": int(heart_rate),
        "spo2": int(spo2)
    }
    try:
        with st.spinner("正在预测，请稍后..."):
            response = requests.post(
                f"{DOCTOR_BACKEND_URL}/predict/{selected_model}",
                json=payload,
                headers={"X-Client-ID": "doctor-app",
                         "X-Doctor-Key": DOCTOR_KEY,
                         "X-Request-ID": req_id
                },
                timeout=10
            )
            result = response.json()
    except (requests.ConnectionError, requests.Timeout):
        st.error(f"服务暂时不可用，请稍后重试。\n\n**追踪代码：{req_id}**")
        st.stop()
    
    if result.get("status") == "error":
        st.error(f"预测失败：{result.get('message', '未知错误')}\n\n**追踪代码：{req_id}**")
        st.stop()
    
    
    if  result['prediction'] == 1:
        st.error("⚠️预测结果：高风险")
    else: 
        st.success("预测结果：低风险")
    st.write(f"患病概率：{result['probability']:.2%}")
    st.write(f"模型版本：{result['model_version']}")
st.divider()
st.caption("⚠️本预测结果仅供医疗参考，不作为诊断依据。最终诊断请以医生判断为准。")