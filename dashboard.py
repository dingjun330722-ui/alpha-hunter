import streamlit as st
import requests
import feedparser
from openai import OpenAI
import datetime
import concurrent.futures
import json
import os
import socket

# ================== 页面配置 ==================
st.set_page_config(page_title="Alpha Hunter V2.4 (穿墙版)", page_icon="⚡", layout="wide")

# ================== 全局设置 ==================
# 1. 放宽超时时间到 30秒 (防止网络波动)
socket.setdefaulttimeout(30)

# 2. 伪装浏览器头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 自定义 CSS
st.markdown("""
<style>
    .card { background-color: #f0f2f6; border-radius: 10px; padding: 20px; border-left: 5px solid #ff4b4b; margin-bottom: 20px; color: #31333F; }
    .card-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
    .card-content { font-size: 14px; line-height: 1.6; }
    .card-source { font-size: 12px; color: #666; margin-top: 15px; font-style: italic; }
    .stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# ================== 配置管理 ==================
SOURCE_FILE = "sources.json"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "api_url": "https://new.wuxuai.com/v1", # 你的API
    "api_key": "",
    "proxy_url": "", # 新增：代理地址
    "models": ["gemini-2.5-pro", "gpt-4o", "glm-4-flash"],
    "selected_model": "gemini-2.5-pro"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config(config_data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

if 'app_config' not in st.session_state:
    st.session_state.app_config = load_config()

def update_config_key(key, value):
    st.session_state.app_config[key] = value
    save_config(st.session_state.app_config)

# ================== AI 分析核心 ==================
def analyze_single_source(source, model, key, url, sys_prompt, proxy):
    result = {"source": source["name"], "status": "failed", "data": None, "error": None}
    
    # === 关键修正：设置环境变量以使用代理 ===
    if proxy and proxy.strip() != "":
        os.environ['http_proxy'] = proxy
        os.environ['https_proxy'] = proxy
    else:
        # 如果没填代理，清除环境变量，防止残留
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)

    if not source.get("enabled", True):
        result["status"] = "skipped"
        return result

    try:
        # 解析 RSS
        feed = feedparser.parse(source["url"], request_headers=HEADERS)
        
        if not feed.entries:
            result["status"] = "empty"
            return result
            
        entry = feed.entries[0]
        content_snippet = entry.get('summary', '')[:800]
        if len(content_snippet) < 10: content_snippet = entry.title # 保底

        # 调用 AI (OpenAI 库会自动读取上面的环境变量代理，或者直连)
        client = OpenAI(api_key=key, base_url=url)
        
        user_prompt = f"【标题】：{entry.title}\n【内容摘要】：{content_snippet}"
        
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=20 
        )
        
        result["status"] = "success"
        result["data"] = {
            "title": entry.title,
            "link": entry.link,
            "summary": entry.get('summary', '无摘要'),
            "ai_analysis": resp.choices[0].message.content,
        }
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

# ================== 侧边栏 ==================
with st.sidebar:
    st.header("⚙️ 穿墙控制台")
    
    with st.expander("🔌 连接配置", expanded=True):
        api_url = st.text_input("接口地址", value=st.session_state.app_config.get("api_url"), key="input_url", on_change=lambda: update_config_key("api_url", st.session_state.input_url))
        api_key = st.text_input("API 密钥", type="password", value=st.session_state.app_config.get("api_key"), key="input_key", on_change=lambda: update_config_key("api_key", st.session_state.input_key))
        
        # === 新增：代理设置 ===
        st.markdown("---")
        st.caption("👇 如果全跳过，请在此填入本地代理地址 (如 http://127.0.0.1:7890)")
        proxy_url = st.text_input("HTTP 代理 (Proxy)", value=st.session_state.app_config.get("proxy_url", ""), placeholder="例如: http://127.0.0.1:7890", key="input_proxy", on_change=lambda: update_config_key("proxy_url", st.session_state.input_proxy))

    st.markdown("### 🤖 模型控制")
    # ... (模型选择部分保持不变，省略以节省空间，功能同上版本) ...
    # 为了保证完整性，我这里保留核心下拉框逻辑
    model_list = st.session_state.app_config.get("models", ["gemini-2.5-pro"])
    current_model = st.session_state.app_config.get("selected_model")
    index = model_list.index(current_model) if current_model in model_list else 0
    selected_model = st.selectbox("选择模型", model_list, index=index, key="model_select", on_change=lambda: update_config_key("selected_model", st.session_state.model_select))
    
    # 刷新按钮逻辑简单化
    if st.button("🔄 刷新模型库"):
         try:
            # 简单刷新逻辑
            os.environ['http_proxy'] = proxy_url
            os.environ['https_proxy'] = proxy_url
            headers = {"Authorization": f"Bearer {api_key}"}
            res = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                models = [item['id'] for item in data['data']] if 'data' in data else [item['id'] for item in data]
                st.session_state.app_config["models"] = models
                save_config(st.session_state.app_config)
                st.success("刷新成功")
                st.rerun()
         except: st.error("刷新失败，请检查网络或密钥")

    st.divider()
    st.markdown("### 📡 情报源管理")
    if 'sources_data' not in st.session_state:
        if os.path.exists(SOURCE_FILE):
             with open(SOURCE_FILE, 'r', encoding='utf-8') as f: st.session_state.sources_data = json.load(f)
        else: st.session_state.sources_data = [{"name": "OpenAI Blog", "url": "https://openai.com/index.xml", "enabled": True}]

    edited_sources = st.data_editor(st.session_state.sources_data, num_rows="dynamic", column_config={"name": "信源名称","url": st.column_config.LinkColumn("RSS链接"),"enabled": st.column_config.CheckboxColumn("启用", default=True)}, key="editor")
    if edited_sources != st.session_state.sources_data:
        st.session_state.sources_data = edited_sources
        with open(SOURCE_FILE, 'w', encoding='utf-8') as f: json.dump(edited_sources, f, ensure_ascii=False, indent=4)

    st.divider()
    default_prompt = "你是一个华尔街顶级情报官。对每条消息进行评分(0-10)。给出简练的【逻辑链】推演和【交易建议】(Long/Short)。风格极度毒舌、功利。"
    system_prompt = st.text_area("AI 人设指令", value=default_prompt, height=100)

# ================== 主界面 ==================
st.title("⚡ Alpha Hunter V2.4 (穿墙版)")

if st.button("🚀 极速扫描 (TURBO SCAN)", type="primary"):
    active_sources = [s for s in st.session_state.sources_data if s.get('enabled', True)]
    
    if not active_sources:
        st.warning("请先添加情报源！")
    else:
        results_container = st.container()
        progress_bar = st.progress(0)
        
        # 传入 proxy 参数
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_source = {
                executor.submit(analyze_single_source, source, selected_model, api_key, api_url, system_prompt, proxy_url): source 
                for source in active_sources
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_source):
                res = future.result()
                completed += 1
                progress_bar.progress(completed / len(active_sources))
                
                if res["status"] == "success":
                    data = res["data"]
                    with results_container:
                        c1, c2 = st.columns([1.5, 1])
                        with c2:
                            st.subheader(f"📄 {res['source']}")
                            st.markdown(f"[{data['title']}]({data['link']})")
                            with st.expander("摘要"): st.write(data['summary'])
                            html_card = f"""<div class="card"><div class="card-title">{data['title']}</div><div class="card-content">{data['summary'][:150]}...</div><div class="card-source">Source: {res['source']}</div></div>"""
                            st.markdown(html_card, unsafe_allow_html=True)
                        with c1:
                            st.subheader("🤖 分析报告")
                            st.info(data['ai_analysis'])
                        st.divider()
                elif res["status"] == "failed":
                    error_msg = res['error']
                    # 优化报错显示
                    if "Connection" in str(error_msg) or "timed out" in str(error_msg):
                        st.warning(f"⚠️ {res['source']} 无法连接 (请检查代理设置)")
                    else:
                        st.error(f"❌ {res['source']}: {error_msg}")