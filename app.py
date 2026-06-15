import streamlit as st
import pandas as pd
from langchain_openai import ChatOpenAI
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

# 1. 页面基本配置
st.set_page_config(page_title="航运数据 AI 助手", layout="wide")
st.title("🚢 航运与大宗商品数据智能查询")
st.markdown("上传你的 Excel 或 CSV 数据，AI 会自动清洗并准备好回答你的任何问题！")

# 2. 初始化缓存
if 'current_df' not in st.session_state:
    st.session_state['current_df'] = None
if 'file_name' not in st.session_state:
    st.session_state['file_name'] = ""

# 3. 弹出式上传与清洗窗口
@st.dialog("📂 选择与上传数据")
def data_selection_dialog():
    st.write("支持上传 `.csv` 或多表单 `.xlsx` 文件")
    uploaded_file = st.file_uploader("上传文件", type=["csv", "xlsx", "xls"], label_visibility="collapsed")
    
    if uploaded_file is not None:
        with st.spinner("⏳ 正在智能读取和清洗数据（多表单 Excel 可能需要几十秒），请稍候..."):
            try:
                # 判断文件类型
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                if file_extension == 'csv':
                    try:
                        df = pd.read_csv(uploaded_file, low_memory=False, encoding='utf-8')
                    except UnicodeDecodeError:
                        uploaded_file.seek(0)
                        df = pd.read_csv(uploaded_file, low_memory=False, encoding='gbk')
                        
                elif file_extension in ['xlsx', 'xls']:
                    # 读取 Excel 中所有的 Sheet
                    all_sheets = pd.read_excel(uploaded_file, sheet_name=None)
                    df_list = [sheet for sheet in all_sheets.values()]
                    df = pd.concat(df_list, ignore_index=True) # 合并成大表
                
                # 智能清洗表头
                if 'CargoType' not in df.columns and 'mmsi' not in df.columns:
                    for i in range(min(20, len(df))):
                        row_vals = [str(x) for x in df.iloc[i].values]
                        if 'CargoType' in row_vals or 'mmsi' in row_vals:
                            df.columns = df.iloc[i]
                            df = df.iloc[i+1:].reset_index(drop=True)
                            break
                            
                st.session_state['current_df'] = df
                st.session_state['file_name'] = uploaded_file.name
                
                st.success(f"✅ 数据加载并合并成功！当前底表共计 {len(df)} 行。")
                if st.button("开始分析", type="primary"):
                    st.rerun()
                    
            except Exception as e:
                st.error(f"处理文件出错: {e}")

# 4. 侧边栏配置 API
with st.sidebar:
    st.header("⚙️ 系统配置")
    api_key = st.text_input("输入你的大模型 API Key", type="password")
    base_url = st.text_input("输入 API Base URL (如使用 DeepSeek 请填入其网址)", value="https://api.deepseek.com/v1")
    model_name = st.text_input("输入模型名称", value="deepseek-chat")

# 5. 网站主干逻辑
if st.button("➕ 点击上传数据文件", type="primary"):
    data_selection_dialog()

st.divider()

if st.session_state['current_df'] is not None:
    df = st.session_state['current_df']
    st.info(f"📁 当前分析数据：**{st.session_state['file_name']}** (包含 {len(df)} 行有效记录)")
    
    with st.expander("点击预览清理后的真实数据"):
        st.dataframe(df.head(5))

    user_query = st.text_input("💬 请输入你想查询的问题：", placeholder="例如：中国2024年铁矿石的进口量是多少？")

    if st.button("开始查询") and user_query:
        if not api_key:
            st.warning("⚠️ 请先在左侧输入你的 API Key")
        else:
            with st.spinner("🤖 AI 正在化身数据分析师，阅读你的表格并写代码计算，请稍候..."):
                try:
                    llm = ChatOpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        model=model_name,
                        temperature=0
                    )
                    
                    agent = create_pandas_dataframe_agent(
                        llm, df, verbose=True, allow_dangerous_code=True, agent_type="openai-tools"
                    )
                    
                    # 💡 核心升级：把复杂规则写进后台的 Prompt 里！
                    prompt = f"""
                    你是一个严谨且极其聪明的航运数据分析师。你的任务是帮用户分析 DataFrame 并给出准确的数值结果。
                    
                    【🚨 你的底层强制执行规则 - 必须绝对遵守】：
                    1. 只要涉及求总量、求和等数学计算（尤其是对 'capacity' 载重量列），**你必须先在代码里使用 `pd.to_numeric(df['对应列名'], errors='coerce')` 强制将其转换为数字类型**，并用 dropna() 清除空值后，再进行求和。绝不可以直接对文本字符串求和！
                    2. 当需要匹配货物名称（如铁矿石、煤炭）或国家名称时，**请务必使用模糊查询**（例如：`df[df['CargoType'].str.contains('铁矿', na=False)]`），不要使用精确等于 `==`，以防止数据名称有空格或多余字符。
                    3. 目的国为中国，可模糊搜索 'arrivecountryCN' 或 'arrivecountry' 列包含 '中国' 或 'CN'。
                    4. 遇到任何由于数据格式导致的错误（如 TypeError, ValueError），请自行反思原因，调整代码并重试。
                    
                    用户现在的提问是大白话：【{user_query}】
                    
                    请结合上述强制规则，写代码计算，并用中文直接给出最终精确的计算数值结果。
                    """
                    
                    response = agent.invoke(prompt)
                    st.success(f"**查询结果：** {response['output']}")
                    
                except Exception as e:
                    st.error(f"计算过程中出现错误：{e}")
