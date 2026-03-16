import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date
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

# 1. APIからのデータ読み込み（地点・年ごとにキャッシュ）
@st.cache_data(ttl=3600)
def load_api_data(year, loc_name):
    lat = LOCATIONS[loc_name]["lat"]
    lon = LOCATIONS[loc_name]["lon"]
    start_str = f"{year}-01-01"
    end_str = f"{year}-12-31"
    today_str = date.today().strftime('%Y-%m-%d')

    res_url = "https://archive-api.open-meteo.com/v1/archive"
    cli_url = "https://climate-api.open-meteo.com/v1/climate"
    
    try:
        # 実績と平年値の取得
        res_data = requests.get(res_url, params={"latitude": lat, "longitude": lon, "start_date": start_str, "end_date": today_str, "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"}).json()
        cli_data = requests.get(cli_url, params={"latitude": lat, "longitude": lon, "start_date": start_str, "end_date": end_str, "models": "best_match", "daily": "temperature_2m_mean"}).json()

        df_act = pd.DataFrame({"年月日": pd.to_datetime(res_data["daily"]["time"]), "平均気温(℃)": res_data["daily"]["temperature_2m_mean"]})
        df_cli = pd.DataFrame({"年月日": pd.to_datetime(cli_data["daily"]["time"]), "平年値平均気温(℃)": cli_data["daily"]["temperature_2m_mean"]})
        
        # 結合
        df = pd.merge(df_cli, df_act, on="年月日", how="left")
        return df
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame()

# 2. 設定（サイドバー）
st.sidebar.header("⚙️ 設定パネル")

# 地点の選択
selected_loc_name = st.sidebar.selectbox("📍 観測地点を選択", list(LOCATIONS.keys()))
loc_data = LOCATIONS[selected_loc_name]

# データの読み込み
current_year = date.today().year
df = load_api_data(current_year, selected_loc_name)

if not df.empty:
    min_date_val = df['年月日'].min().date()
    real_today = date.today()

    start_date = st.sidebar.date_input("📅 積算開始日", value=date(current_year, 1, 1))
    today_date = st.sidebar.date_input("📅 現在の日付 (これ以降は平年値)", value=real_today)
    target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)
    base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)

    # 3. 計算
    mask = df['年月日'].dt.date >= start_date
    calc_df = df[mask].copy()
    
    def get_effective_temp(row):
        # 実績があれば実績、なければ平年値を使用
        if row['年月日'].date() < today_date and not pd.isna(row['平均気温(℃)']):
            temp = row['平均気温(℃)']
        else:
            temp = row['平年値平均気温(℃)']
        return max(0, temp - base_temp)

    calc_df['適用気温'] = calc_df.apply(get_effective_temp, axis=1)
    calc_df['積算温度'] = calc_df['適用気温'].cumsum()

    # 到達推定
    reach_df = calc_df[calc_df['積算温度'] >= target_temp]
    
    st.markdown(f"### 📍 {selected_loc_name} の推定結果")
    if not reach_df.empty:
        reach_date = reach_df.iloc[0]['年月日'].date()
        st.success(f"🎉 目標の積算温度 **{target_temp}℃** に到達する推定日は **{reach_date}** です！")
    else:
        st.warning(f"⚠️ データ期間内に目標温度に到達しません。")

    # グラフ表示
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(calc_df['年月日'], calc_df['積算温度'], label='積算温度', color='#ff7f0e', linewidth=2)
    ax.axhline(y=target_temp, color='#d62728', linestyle='--', label=f'目標 ({target_temp}℃)')
    if not reach_df.empty:
        ax.axvline(x=reach_df.iloc[0]['年月日'], color='#1f77b4', linestyle=':', label=f'到達日 ({reach_date})')
    
    ax.set_xlabel('日付')
    ax.set_ylabel('積算温度 (℃)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)

    # データ詳細（以前のアプリのように、数値をしっかり確認できるように）
    with st.expander("📝 計算データの詳細を確認"):
        # 表示用にフォーマットを整える
        display_df = calc_df[['年月日', '平均気温(℃)', '平年値平均気温(℃)', '適用気温', '積算温度']].copy()
        st.dataframe(display_df.style.format({
            '平均気温(℃)': '{:.1f}',
            '平年値平均気温(℃)': '{:.1f}',
            '適用気温': '{:.1f}',
            '積算温度': '{:.1f}'
        }), use_container_width=True)

        # CSV保存ボタン
        st.download_button(
            label="このデータをCSVとして保存",
            data=display_df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"temp_data_{selected_loc_name}_{date.today()}.csv",
            mime='text/csv',
        )