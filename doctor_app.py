import os
import uuid

import requests
import streamlit as st

DOCTOR_BACKEND_URL = os.getenv("DOCTOR_BACKEND_URL", "http://127.0.0.1:9002")
DOCTOR_KEY = os.getenv("DOCTOR_API_KEY", "doctor_secret")

st.set_page_config(page_title="医疗模型预测平台", layout="wide", page_icon="🏥")

# 注入全局 CSS 样式
st.markdown("""
<style>
    .main-title {
        color: #1E90FF;
        font-family: 'Helvetica Neue', sans-serif;
        text-align: center;
        margin-bottom: 30px;
        font-weight: bold;
    }
    .stButton>button {
        width: 100%;
        background-color: #1E90FF;
        color: white;
        border-radius: 8px;
        height: 3em;
        font-size: 16px;
    }
    .stButton>button:hover {
        background-color: #4169E1;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>🏥 智能医疗辅助诊断平台</h1>", unsafe_allow_html=True)

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

col_input, col_result = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("📋 患者信息录入")
    if not models:
        st.warning("⚠️ 当前没有可用的模型，请等待运维人员部署。")
    selected_model = st.selectbox("选择模型", models)
    st.divider()
    
    age = st.number_input("年龄", value=60, min_value=0, max_value=120)
    heart_rate = st.number_input("心率", value=85, min_value=20, max_value=250)
    spo2 = st.number_input("血氧", value=95, min_value=0, max_value=100)
    
    st.divider()
    predict_clicked = st.button("🚀 开始预测", use_container_width=True)

with col_result:
    st.subheader("📊 诊断结果")
    if "prediction_result" not in st.session_state:
        st.info("请在左侧输入患者信息，然后点击预测。")
    else:
        res = st.session_state.prediction_result
        if res.get("status") == "success":
            if res['prediction'] == 1:
                st.error(f"⚠️ 预测结果：高风险\n\n患病概率：{res['probability']:.2%}")
            else:
                st.success(f"✅ 预测结果：低风险\n\n患病概率：{res['probability']:.2%}")
            
            # 把模型版本号和追踪代码收进一个“小抽屉”里，默认隐藏
            with st.expander("ℹ️ 技术详情"):
                st.caption(f"模型版本：{res['model_version']}")
                st.caption(f"追踪代码：{st.session_state.req_id}")
                st.caption("注：若系统发生报错，请将以上追踪代码提供给运维人员。")
        else:
            st.error(f"预测失败：{res.get('message', '未知错误')}\n\n**追踪代码：{st.session_state.req_id}**")

if predict_clicked:
    req_id = str(uuid.uuid4())
    st.session_state.req_id = req_id
    payload = {
        "age": int(age),
        "heart_rate": int(heart_rate),
        "spo2": int(spo2)
    }
    with st.spinner("正在预测，请稍后..."):
        try:
            response = requests.post(
                f"{DOCTOR_BACKEND_URL}/predict/{selected_model}",
                json=payload,
                headers={
                    "X-Client-ID": "doctor-app",
                    "X-Doctor-Key": DOCTOR_KEY,
                    "X-Request-ID": req_id
                },
                timeout=10
            )
            st.session_state.prediction_result = response.json()
            st.rerun()
        except (requests.ConnectionError, requests.Timeout):
            st.session_state.prediction_result = {"status": "error", "message": "服务暂时不可用，请稍后重试。"}
            st.rerun()

st.divider()
st.caption("⚠️ 本预测结果仅供医疗参考，不作为诊断依据。最终诊断请以医生判断为准。")