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
st.set_page_config(page_title="Alpha Hunter V2.5 (云端增强版)", page_icon="⚡", layout="wide")

# 全局超时设置
socket.setdefaulttimeout(30)

# 伪装成真实的浏览器（这是关键）
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
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
    "api_url": "https://new.wuxuai.com/v1",
    "api_key": "",
    "proxy_url": "", 
    "models": ["gemini-2.5-pro", "gpt-4o", "glm-4-flash"],
    "selected_model": "gemini-2.5-pro"
}

def load_config():
    if not os.path.exists(CONFIG_FILE): return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return DEFAULT_CONFIG

def save_config(config_data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

if 'app_config' not in st.session_state:
    st.session_state.app_config = load_config()

def update_config_key(key, value):
    st.session_state.app_config[key] = value
    save_config(st.session_state.app_config)

# ================== 核心：增强型抓取函数 ==================
def fetch_feed_data(url, proxy):
    """
    使用 Requests 库进行强力抓取，绕过反爬虫
    """
    proxies = None
    if proxy and proxy.strip():
        proxies = {"http": proxy, "https": proxy}
    
    try:
        # 第一层尝试：直接用 feedparser
        d = feedparser.parse(url) # 不带 headers 先试一次
        if d.entries:
            return d
            
        # 第二层尝试：模拟浏览器请求
        response = requests.get(url, headers=HEADERS, proxies=proxies, timeout=20)
        response.raise_for_status()
        # 将下载的内容喂给 feedparser
        return feedparser.parse(response.content)
        
    except Exception as e:
        raise e

# ================== AI 分析核心 ==================
def analyze_single_source(source, model, key, url, sys_prompt, proxy):
    result = {"source": source["name"], "status": "failed", "data": None, "error": None}
    
    if not source.get("enabled", True):
        result["status"] = "skipped"
        return result

    try:
        # === 核心改动：使用增强版抓取 ===
        feed = fetch_feed_data(source["url"], proxy)
        
        if not feed.entries:
            result["status"] = "empty" # 真的没抓到内容
            return result
            
        entry = feed.entries[0]
        content_snippet = entry.get('summary', '')[:800]
        if len(content_snippet) < 10: content_snippet = entry.title 

        # 即使抓取成功，如果 Key 没填对，AI 也会报错，这里加个判断
        if not key:
            raise Exception("未填写 API Key")

        # 调用 AI
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
    st.header("⚙️ 云端控制台")
    
    with st.expander("🔌 连接配置", expanded=True):
        api_url = st.text_input("接口地址", value=st.session_state.app_config.get("api_url"), key="input_url", on_change=lambda: update_config_key("api_url", st.session_state.input_url))
        api_key = st.text_input("API 密钥", type="password", value=st.session_state.app_config.get("api_key"), key="input_key", on_change=lambda: update_config_key("api_key", st.session_state.input_key))
        
        # 代理设置（重点提示）
        st.markdown("---")
        proxy_url = st.text_input("HTTP 代理 (云端请留空！)", value=st.session_state.app_config.get("proxy_url", ""), placeholder="本地填 http://127.0.0.1:7890，云端必须为空", key="input_proxy", on_change=lambda: update_config_key("proxy_url", st.session_state.input_proxy))
        if proxy_url and "127.0.0.1" in proxy_url:
            st.warning("⚠️ 警告：检测到你在云端使用了本地代理地址，这会导致无法连接！请清空此栏。")

    st.markdown("### 🤖 模型控制")
    model_list = st.session_state.app_config.get("models", ["gemini-2.5-pro"])
    current_model = st.session_state.app_config.get("selected_model")
    index = model_list.index(current_model) if current_model in model_list else 0
    selected_model = st.selectbox("选择模型", model_list, index=index, key="model_select", on_change=lambda: update_config_key("selected_model", st.session_state.model_select))
    
    # 简单的刷新按钮
    if st.button("🔄 刷新模型库"):
         try:
            # 刷新时不走代理，除非用户强行填了
            headers = {"Authorization": f"Bearer {api_key}"}
            res = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                models = [item['id'] for item in data['data']] if 'data' in data else [item['id'] for item in data]
                st.session_state.app_config["models"] = models
                save_config(st.session_state.app_config)
                st.success("刷新成功")
                st.rerun()
         except Exception as e: st.error(f"刷新失败: {e}")

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
st.title("⚡ Alpha Hunter V2.5 (云端强力版)")

if st.button("🚀 极速扫描 (TURBO SCAN)", type="primary"):
    active_sources = [s for s in st.session_state.sources_data if s.get('enabled', True)]
    
    if not active_sources:
        st.warning("请先添加情报源！")
    else:
        results_container = st.container()
        progress_bar = st.progress(0)
        
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
                    st.error(f"❌ {res['source']}: {res['error']}")