import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
import requests
import warnings

# グラフの日本語文字化け対策
warnings.filterwarnings('ignore')
try:
    plt.rcParams['font.family'] = 'Meiryo' 
except:
    pass

st.set_page_config(page_title="積算温度 到達日推定アプリ", layout="wide")
st.title("🌡️ 積算温度 到達日推定アプリ")

# --- 地点データの定義 ---
LOCATIONS = {
    "鹿屋市": {"lat": 31.3783, "lon": 130.8522},
    "出水市": {"lat": 32.0778, "lon": 130.3556},
    "南さつま市": {"lat": 31.4150, "lon": 130.3200}
}

@st.cache_data(ttl=3600)
def load_api_data(year, loc_name):
    lat = LOCATIONS[loc_name]["lat"]
    lon = LOCATIONS[loc_name]["lon"]
    
    # エラー回避のため、実績は「3日前」までを指定する（確実なデータ）
    safe_end_date = (date.today() - timedelta(days=3)).strftime('%Y-%m-%d')
    start_str = f"{year}-01-01"
    end_str = f"{year}-12-31"

    # 1. 実績データの取得
    res_url = "https://archive-api.open-meteo.com/v1/archive"
    res_params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": safe_end_date,
        "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
    }
    
    # 2. 平年値データの取得
    cli_url = "https://climate-api.open-meteo.com/v1/climate"
    cli_params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": end_str,
        "models": "best_match", "daily": "temperature_2m_mean"
    }

    try:
        res_resp = requests.get(res_url, params=res_params).json()
        cli_resp = requests.get(cli_url, params=cli_params).json()

        # 'daily' キーが存在するかチェック
        if "daily" not in res_resp or "daily" not in cli_resp:
            st.error("APIから有効なデータが返されませんでした。しばらく時間をおいて試してください。")
            return pd.DataFrame()

        df_act = pd.DataFrame({"年月日": pd.to_datetime(res_resp["daily"]["time"]), "平均気温(℃)": res_resp["daily"]["temperature_2m_mean"]})
        df_cli = pd.DataFrame({"年月日": pd.to_datetime(cli_resp["daily"]["time"]), "平年値平均気温(℃)": cli_resp["daily"]["temperature_2m_mean"]})
        
        return pd.merge(df_cli, df_act, on="年月日", how="left")
    except Exception as e:
        st.error(f"接続エラーが発生しました: {e}")
        return pd.DataFrame()

# --- メイン処理 ---
selected_loc_name = st.sidebar.selectbox("📍 観測地点を選択", list(LOCATIONS.keys()))
df = load_api_data(date.today().year, selected_loc_name)

if not df.empty:
    # (以下、以前の計算・グラフ表示ロジックと同じ)
    start_date = st.sidebar.date_input("📅 積算開始日", value=date(date.today().year, 1, 1))
    today_date = st.sidebar.date_input("📅 切り替え日 (これ以降は平年値)", value=date.today() - timedelta(days=3))
    target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)
    base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)

    mask = df['年月日'].dt.date >= start_date
    calc_df = df[mask].copy()
    
    calc_df['適用気温'] = calc_df.apply(lambda r: max(0, (r['平均気温(℃)'] if r['年月日'].date() < today_date and not pd.isna(r['平均気温(℃)']) else r['平年値平均気温(℃)']) - base_temp), axis=1)
    calc_df['積算温度'] = calc_df['適用気温'].cumsum()

    reach_df = calc_df[calc_df['積算温度'] >= target_temp]
    
    st.markdown(f"### 📍 {selected_loc_name} の推定結果")
    if not reach_df.empty:
        st.success(f"🎉 目標到達推定日は **{reach_df.iloc[0]['年月日'].date()}** です！")
    else:
        st.warning("期間内に到達しません。")

    st.line_chart(calc_df.set_index("年月日")["積算温度"])
    with st.expander("詳細データ"):
        st.dataframe(calc_df)
