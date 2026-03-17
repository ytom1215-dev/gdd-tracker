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
    
    # 日付から「月-日」だけを取り出し、1年分の平年値カレンダーを作る
    df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')
    normals_df = df.groupby('MM-DD')['平年値平均気温(℃)'].mean().reset_index()
    return normals_df

# 2. Open-Meteoから「今年の実績」だけを軽く読み込む関数
@st.cache_data(ttl=3600)
def load_api_current_year(year):
    # 鹿屋市付近の座標
    lat, lon = 31.3783, 130.8522 
    
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
# CSVの読み込みチェック
try:
    df_normals = load_csv_normals()
except FileNotFoundError:
    st.error("⚠️ 'data (1).csv' が見つかりません。アプリと同じフォルダに配置してください。")
    st.stop()

# 今年のデータをAPIから取得
current_year = date.today().year
df_actuals = load_api_current_year(current_year)

# 3. データの結合（今年1年分のベースを作り、平年値と実績を当てはめる）
base_dates = pd.date_range(start=f"{current_year}-01-01", end=f"{current_year}-12-31")
df = pd.DataFrame({"年月日": base_dates})
df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')

# 平年値を結合
df = pd.merge(df, df_normals, on='MM-DD', how='left')

# 実績を結合
if not df_actuals.empty:
    df = pd.merge(df, df_actuals, on='年月日', how='left')
else:
    df['平均気温(℃)'] = None # 万が一APIが失敗した場合は空にする

df.drop(columns=['MM-DD'], inplace=True)

# --- UIと計算ロジック ---
st.sidebar.header("⚙️ 設定パネル")
start_date = st.sidebar.date_input("📅 積算開始日", value=date(current_year, 1, 1))
today_date = date.today() - timedelta(days=2) # 実績として信頼できる2日前を境界にする

base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)
target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)

calc_df = df[df['年月日'].dt.date >= start_date].copy()

def get_effective_temp(row):
    # 実績期間かつデータがあれば実績を、なければ平年値を採用
    if row['年月日'].date() <= today_date and not pd.isna(row['平均気温(℃)']):
        val = row['平均気温(℃)']
    else:
        val = row['平年値平均気温(℃)']
        
    if pd.isna(val): val = 0 # 欠損時の安全対策
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

# グラフ
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
