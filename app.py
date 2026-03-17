import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import requests
import plotly.graph_objects as go  # 🌟 ここが新しくなりました！

st.set_page_config(page_title="積算温度 到達日推定アプリ", layout="wide")
st.title("🌡️ 積算温度 到達日推定アプリ (ハイブリッド版)")

# 1. CSVから「平年値」を読み込む関数
@st.cache_data
def load_csv_normals():
    try:
        df = pd.read_csv("data (1).csv", encoding="utf-8-sig")
    except:
        df = pd.read_csv("data (1).csv", encoding="cp932")
    
    df.columns = df.columns.str.strip()
    df['年月日'] = pd.to_datetime(df['年月日'])
    
    df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')
    normals_df = df.groupby('MM-DD')['平年値平均気温(℃)'].mean().reset_index()
    return normals_df

# 2. Open-Meteoから「今年の実績」だけを軽く読み込む関数
@st.cache_data(ttl=3600)
def load_api_current_year(year):
    lat, lon = 31.3783, 130.8522 # 鹿屋市（鹿児島市にする場合は 31.5600, 130.5581 に変更）
    
    start_str = f"{year}-01-01"
    safe_today = (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": safe_today,
        "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
    }
    
    try:
        resp = requests.get(url, params=params).json()
        if "error" in resp:
            st.warning(f"⚠️ 今年のデータ取得エラー: {resp.get('reason')}")
            return pd.DataFrame()
            
        df_act = pd.DataFrame({
            "年月日": pd.to_datetime(resp["daily"]["time"]),
            "平均気温(℃)": resp["daily"]["temperature_2m_mean"]
        })
        return df_act
    except Exception as e:
        st.warning(f"⚠️ API通信エラー: {e}")
        return pd.DataFrame()

# --- メイン処理 ---
try:
    df_normals = load_csv_normals()
except FileNotFoundError:
    st.error("⚠️ 'data (1).csv' が見つかりません。アプリと同じフォルダに配置してください。")
    st.stop()

current_year = date.today().year
df_actuals = load_api_current_year(current_year)

base_dates = pd.date_range(start=f"{current_year}-01-01", end=f"{current_year}-12-31")
df = pd.DataFrame({"年月日": base_dates})
df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')

df = pd.merge(df, df_normals, on='MM-DD', how='left')

if not df_actuals.empty:
    df = pd.merge(df, df_actuals, on='年月日', how='left')
else:
    df['平均気温(℃)'] = None 

df.drop(columns=['MM-DD'], inplace=True)

# --- UIと計算ロジック ---
st.sidebar.header("⚙️ 設定パネル")
start_date = st.sidebar.date_input("📅 積算開始日", value=date(current_year, 1, 1))
today_date = date.today() - timedelta(days=2) 

base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)
target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)

calc_df = df[df['年月日'].dt.date >= start_date].copy()

def get_effective_temp(row):
    if row['年月日'].date() <= today_date and not pd.isna(row['平均気温(℃)']):
        val = row['平均気温(℃)']
    else:
        val = row['平年値平均気温(℃)']
        
    if pd.isna(val): val = 0 
    return max(0, val - base_temp)

calc_df['適用気温'] = calc_df.apply(get_effective_temp, axis=1)
calc_df['積算温度'] = calc_df['適用気温'].cumsum()

reach_df = calc_df[calc_df['積算温度'] >= target_temp]

st.markdown("### 📍 ハイブリッド推定結果")
if not reach_df.empty:
    reach_date = reach_df.iloc[0]['年月日'].date()
    st.success(f"🎉 目標の積算温度 **{target_temp}℃** に到達する推定日は **{reach_date}** です！")
else:
    st.warning("⚠️ 期間内に到達しません。")

# 🌟 ここから Plotly の新しいグラフ描画コード 🌟
fig = go.Figure()

# 積算温度のライン
fig.add_trace(go.Scatter(
    x=calc_df['年月日'], 
    y=calc_df['積算温度'], 
    mode='lines', 
    name='積算温度',
    line=dict(color='#ff7f0e', width=3)
))

# 目標温度の水平線
fig.add_hline(
    y=target_temp, 
    line_dash="dash", 
    line_color="#d62728", 
    annotation_text=f"目標 ({target_temp}℃)", 
    annotation_position="top left"
)

# 到達日の垂直線
if not reach_df.empty:
    fig.add_vline(
        x=reach_df.iloc[0]['年月日'], 
        line_dash="dot", 
        line_color="#1f77b4", 
        annotation_text=f"到達日 ({reach_date})", 
        annotation_position="bottom right"
    )

# グラフのレイアウト設定
fig.update_layout(
    xaxis_title="日付",
    yaxis_title="積算温度 (℃)",
    hovermode="x unified",  # マウスを乗せると詳細が出る設定
    margin=dict(l=20, r=20, t=30, b=20)
)

# グラフを表示
st.plotly_chart(fig, use_container_width=True)

with st.expander("📝 計算データの詳細を確認"):
    display_df = calc_df[['年月日', '平均気温(℃)', '平年値平均気温(℃)', '適用気温', '積算温度']].copy()
    st.dataframe(display_df.style.format({
        '平均気温(℃)': '{:.1f}',
        '平年値平均気温(℃)': '{:.1f}',
        '適用気温': '{:.1f}',
        '積算温度': '{:.1f}'
    }), use_container_width=True)

    st.download_button(
        label="このデータをCSVとして保存",
        data=display_df.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"hybrid_temp_data_{date.today()}.csv",
        mime='text/csv',
    )
