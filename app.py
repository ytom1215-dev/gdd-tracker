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

    try:
        # 1. 天気予報API（過去90日分 ＋ 未来14日分の高精度予測を取得）
        # ※ こちらのAPIは制限が緩く、エラーになりにくいです
        forecast_url = "https://api.open-meteo.com/v1/forecast"
        fcst_params = {
            "latitude": lat, "longitude": lon,
            "past_days": 90,        # 年初からのデータをカバー
            "forecast_days": 16,    # 向こう2週間の予報をカバー
            "daily": "temperature_2m_mean",
            "timezone": "Asia/Tokyo"
        }
        fcst_resp = requests.get(forecast_url, params=fcst_params).json()

        if "error" in fcst_resp:
            st.error(f"予報データ取得エラー: {fcst_resp.get('reason')}")
            return pd.DataFrame()

        df_curr = pd.DataFrame({
            "年月日": pd.to_datetime(fcst_resp["daily"]["time"]),
            "予報・実績気温(℃)": fcst_resp["daily"]["temperature_2m_mean"]
        })

        # 2. 過去API（データ量を10年→直近3年に減らして制限を回避）
        archive_url = "https://archive-api.open-meteo.com/v1/archive"
        hist_params = {
            "latitude": lat, "longitude": lon,
            "start_date": "2021-01-01", "end_date": "2023-12-31",
            "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
        }
        hist_resp = requests.get(archive_url, params=hist_params).json()

        if "error" in hist_resp:
            st.warning("⚠️ 過去データが制限により取得できませんでした。簡易平年値で計算します。")
            df_hist = pd.DataFrame()
        else:
            df_hist = pd.DataFrame({
                "date": pd.to_datetime(hist_resp["daily"]["time"]),
                "temp": hist_resp["daily"]["temperature_2m_mean"]
            })

        # 3. 平年値の算出
        base_dates = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31")
        df = pd.DataFrame({"年月日": base_dates})
        df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')

        if not df_hist.empty:
            df_hist['MM-DD'] = df_hist['date'].dt.strftime('%m-%d')
            normal_temps = df_hist.groupby('MM-DD')['temp'].mean().reset_index()
            normal_temps.rename(columns={'temp': '平年値(℃)'}, inplace=True)
            df = pd.merge(df, normal_temps, on='MM-DD', how='left')
        else:
            # 万が一過去データが取得できなかった場合の緊急ダミー値（エラー停止を防ぐ）
            df['平年値(℃)'] = 15.0 

        # 予報・実績データをマージ
        df = pd.merge(df, df_curr, on='年月日', how='left')
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
    target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)
    base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)

    calc_df = df[df['年月日'].dt.date >= start_date].copy()
    
    def get_effective_temp(row):
        # 14日先までの「実績・予報データ」があればそれを使い、それより未来は「平年値」を使う
        val = row['予報・実績気温(℃)'] if not pd.isna(row['予報・実績気温(℃)']) else row['平年値(℃)']
        if pd.isna(val): val = 0 
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
        display_df = calc_df[['年月日', '予報・実績気温(℃)', '平年値(℃)', '適用気温', '積算温度']].copy()
        st.dataframe(display_df.style.format({
            '予報・実績気温(℃)': '{:.1f}',
            '平年値(℃)': '{:.1f}',
            '適用気温': '{:.1f}',
            '積算温度': '{:.1f}'
        }), use_container_width=True)

        st.download_button(
            label="このデータをCSVとして保存",
            data=display_df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"temp_data_{selected_loc_name}_{date.today()}.csv",
            mime='text/csv',
        )
