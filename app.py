import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
import requests
import warnings

# 日本語表示対策
warnings.filterwarnings('ignore')
try:
    plt.rcParams['font.family'] = 'Meiryo' 
except:
    pass

st.set_page_config(page_title="積算温度 到達日推定アプリ", layout="wide")
st.title("🌡️ 積算温度 到達日推定アプリ")

# 地点リストに種子島を追加
LOCATIONS = {
    "鹿屋市": {"lat": 31.3783, "lon": 130.8522},
    "出水市": {"lat": 32.0778, "lon": 130.3556},
    "南さつま市": {"lat": 31.4150, "lon": 130.3200},
    "西之表市（種子島）": {"lat": 30.7275, "lon": 130.9936}
}

@st.cache_data(ttl=3600)
def load_api_data(year, loc_name):
    lat = LOCATIONS[loc_name]["lat"]
    lon = LOCATIONS[loc_name]["lon"]
    archive_url = "https://archive-api.open-meteo.com/v1/archive"

    try:
        # 1. 過去10年分のデータから「平年値」をアプリ内で自動計算
        hist_params = {
            "latitude": lat, "longitude": lon,
            "start_date": "2014-01-01", "end_date": "2023-12-31",
            "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
        }
        hist_resp = requests.get(archive_url, params=hist_params).json()

        # エラーの内容を画面に表示するための処理
        if "error" in hist_resp:
            st.error(f"過去データの取得エラー: {hist_resp.get('reason')}")
            return pd.DataFrame()

        df_hist = pd.DataFrame({
            "date": pd.to_datetime(hist_resp["daily"]["time"]),
            "temp": hist_resp["daily"]["temperature_2m_mean"]
        })
        
        # 月-日でグループ化して10年間の平均をとる（超高精度な平年値）
        df_hist['MM-DD'] = df_hist['date'].dt.strftime('%m-%d')
        normal_temps = df_hist.groupby('MM-DD')['temp'].mean().reset_index()
        normal_temps.rename(columns={'temp': '平年値平均気温(℃)'}, inplace=True)

        # 2. 今年（実績）のデータを取得
        today = date.today()
        safe_today = (today - timedelta(days=2)).strftime('%Y-%m-%d')
        curr_params = {
            "latitude": lat, "longitude": lon,
            "start_date": f"{year}-01-01", "end_date": safe_today,
            "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
        }
        curr_resp = requests.get(archive_url, params=curr_params).json()

        if "error" in curr_resp:
            st.error(f"今年の実績データ取得エラー: {curr_resp.get('reason')}")
            return pd.DataFrame()

        df_act = pd.DataFrame({
            "年月日": pd.to_datetime(curr_resp["daily"]["time"]),
            "平均気温(℃)": curr_resp["daily"]["temperature_2m_mean"]
        })

        # 3. カレンダーを作成して結合
        base_dates = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31")
        df = pd.DataFrame({"年月日": base_dates})
        df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')
        
        # 平年値と実績をマージ
        df = pd.merge(df, normal_temps, on='MM-DD', how='left')
        df = pd.merge(df, df_act, on='年月日', how='left')
        
        # 不要な列を削除
        df.drop(columns=['MM-DD'], inplace=True)

        return df

    except Exception as e:
        st.error(f"通信エラーが発生しました: {e}")
        return pd.DataFrame()

# --- メインロジック ---
selected_loc_name = st.sidebar.selectbox("📍 観測地点を選択", list(LOCATIONS.keys()))
current_year = date.today().year
df = load_api_data(current_year, selected_loc_name)

if not df.empty:
    st.sidebar.markdown("---")
    start_date = st.sidebar.date_input("📅 積算開始日", value=date(current_year, 1, 1))
    today_date = date.today() - timedelta(days=2)
    target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)
    base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)

    calc_df = df[df['年月日'].dt.date >= start_date].copy()
    
    def get_effective_temp(row):
        val = row['平均気温(℃)'] if row['年月日'].date() <= today_date and not pd.isna(row['平均気温(℃)']) else row['平年値平均気温(℃)']
        if pd.isna(val): val = 0 # 安全対策
        return max(0, val - base_temp)

    calc_df['適用気温'] = calc_df.apply(get_effective_temp, axis=1)
    calc_df['積算温度'] = calc_df['適用気温'].cumsum()

    reach_df = calc_df[calc_df['積算温度'] >= target_temp]
    
    st.subheader(f"📍 {selected_loc_name} の推定結果")
    if not reach_df.empty:
        st.success(f"🎉 目標到達推定日: **{reach_df.iloc[0]['年月日'].date()}**")
    else:
        st.warning("期間内に到達しません。")

    st.line_chart(calc_df.set_index("年月日")["積算温度"])
    
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
            file_name=f"temp_data_{selected_loc_name}_{date.today()}.csv",
            mime='text/csv',
        )
