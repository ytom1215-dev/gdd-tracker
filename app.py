import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import requests
import plotly.graph_objects as go
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="積算温度 到達日推定アプリ", layout="wide")
st.title("🌡️ 積算温度 到達日推定アプリ (8地点ハイブリッド版)")

# --- 観測地点の定義（8地点分の緯度経度） ---
LOCATIONS = {
    "南さつま市": {"lat": 31.4150, "lon": 130.3200},
    "金峰町大野": {"lat": 31.4360, "lon": 130.3540},
    "徳之島町": {"lat": 27.7611, "lon": 129.0219},
    "和泊町": {"lat": 27.3845, "lon": 128.6586},
    "鹿屋市": {"lat": 31.3783, "lon": 130.8522},
    "長島町": {"lat": 32.1883, "lon": 130.1442},
    "根占町": {"lat": 31.1961, "lon": 130.7672},
    "西之表市": {"lat": 30.7275, "lon": 130.9936}
}

# 1. CSVから「選択した地点の平年値」を読み込む関数
@st.cache_data
def load_csv_normals(loc_name):
    try:
        df = pd.read_csv("data (1).csv", encoding="utf-8-sig")
    except:
        df = pd.read_csv("data (1).csv", encoding="cp932")
    
    df.columns = df.columns.str.strip()
    df['年月日'] = pd.to_datetime(df['年月日'])
    
    # CSV内に選択された地点の列があるかチェック
    if loc_name not in df.columns:
        st.error(f"⚠️ CSVファイルに「{loc_name}」の列が見つかりません。列名が完全に一致しているか確認してください。")
        st.stop()
    
    # 選択した地点のデータだけを抽出して1年分の平年値カレンダーを作る
    df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')
    normals_df = df.groupby('MM-DD')[loc_name].mean().reset_index()
    # 後の計算プログラムに合うように列名を統一
    normals_df.rename(columns={loc_name: '平年値平均気温(℃)'}, inplace=True)
    return normals_df

# 2. Open-Meteoから「選択地点の今年の実績」だけを読み込む関数
@st.cache_data(ttl=3600)
def load_api_target_year(year, loc_name):
    lat = LOCATIONS[loc_name]["lat"]
    lon = LOCATIONS[loc_name]["lon"]
    
    start_str = f"{year}-01-01"
    
    # 過去の年の場合は12月31日まで、今年の場合は2日前までを取得
    if year == date.today().year:
        end_str = (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
    else:
        end_str = f"{year}-12-31"
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": end_str,
        "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
    }
    
    try:
        resp = requests.get(url, params=params).json()
        if "error" in resp:
            st.warning(f"⚠️ データ取得エラー: {resp.get('reason')}")
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
st.sidebar.header("⚙️ 設定パネル")

# 対象年と観測地点の選択
current_year = date.today().year
target_year = st.sidebar.selectbox("📅 対象年を選択", list(range(current_year, 2014, -1)))
selected_loc_name = st.sidebar.selectbox("📍 観測地点を選択", list(LOCATIONS.keys()))

# データの読み込み
df_normals = load_csv_normals(selected_loc_name)
df_actuals = load_api_target_year(target_year, selected_loc_name)

# カレンダーの生成と結合
base_dates = pd.date_range(start=f"{target_year}-01-01", end=f"{target_year}-12-31")
df = pd.DataFrame({"年月日": base_dates})
df['MM-DD'] = df['年月日'].dt.strftime('%m-%d')

# 平年値（CSV）と実績（API）を結合
df = pd.merge(df, df_normals, on='MM-DD', how='left')

if not df_actuals.empty:
    df = pd.merge(df, df_actuals, on='年月日', how='left')
else:
    df['平均気温(℃)'] = None 

df.drop(columns=['MM-DD'], inplace=True)

# --- UIと計算ロジック ---
start_date = st.sidebar.date_input("📅 積算開始日", value=date(target_year, 1, 1))

base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5)
target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)

calc_df = df[df['年月日'].dt.date >= start_date].copy()

is_current_year = (target_year == current_year)
today_date = date.today() - timedelta(days=2)

def get_effective_temp(row):
    # 過去の年は全て実績。今年の場合は2日前までが実績。それ以外は各地点の平年値（CSV）。
    if (not is_current_year and not pd.isna(row['平均気温(℃)'])) or \
       (is_current_year and row['年月日'].date() <= today_date and not pd.isna(row['平均気温(℃)'])):
        val = row['平均気温(℃)']
    else:
        val = row['平年値平均気温(℃)']
        
    if pd.isna(val): val = 0 
    return max(0, val - base_temp)

calc_df['適用気温'] = calc_df.apply(get_effective_temp, axis=1)
calc_df['積算温度'] = calc_df['適用気温'].cumsum()

reach_df = calc_df[calc_df['積算温度'] >= target_temp]

st.markdown(f"### 📍 {selected_loc_name} ({target_year}年) の推定結果")
if not reach_df.empty:
    reach_date = reach_df.iloc[0]['年月日'].date()
    st.success(f"🎉 目標の積算温度 **{target_temp}℃** に到達する推定日は **{reach_date}** です！")
else:
    st.warning("⚠️ 期間内に到達しません。")

# --- インタラクティブグラフ (Plotly) ---
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=calc_df['年月日'], 
    y=calc_df['積算温度'], 
    mode='lines', 
    name='積算温度',
    line=dict(color='#ff7f0e', width=3)
))

fig.add_hline(
    y=target_temp, 
    line_dash="dash", 
    line_color="#d62728", 
    annotation_text=f"目標 ({target_temp}℃)", 
    annotation_position="top left"
)

if not reach_df.empty:
    reach_date_str = reach_df.iloc[0]['年月日'].strftime('%Y-%m-%d')
    
    fig.add_vline(x=reach_date_str, line_dash="dot", line_color="#1f77b4")
    
    fig.add_annotation(
        x=reach_date_str, 
        y=target_temp / 2,
        text=f"到達日 ({reach_date})", 
        showarrow=False,
        xanchor="left",
        xshift=5,
        font=dict(color="#1f77b4"),
        bgcolor="rgba(255,255,255,0.7)"
    )

fig.update_layout(
    xaxis_title="日付",
    yaxis_title="積算温度 (℃)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=30, b=20)
)

st.plotly_chart(fig, use_container_width=True)

# --- 詳細データとCSV出力 ---
with st.expander("📝 計算データの詳細を確認"):
    display_df = calc_df[['年月日', '平均気温(℃)', '平年値平均気温(℃)', '適用気温', '積算温度']].copy()
    
    # 表示上の列名を分かりやすく変更
    display_df.rename(columns={'平年値平均気温(℃)': f'{selected_loc_name}の平年値(℃)'}, inplace=True)
    
    st.dataframe(display_df.style.format({
        '平均気温(℃)': '{:.1f}',
        f'{selected_loc_name}の平年値(℃)': '{:.1f}',
        '適用気温': '{:.1f}',
        '積算温度': '{:.1f}'
    }), use_container_width=True)

    st.download_button(
        label="このデータをCSVとして保存",
        data=display_df.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"agri_temp_{selected_loc_name}_{target_year}.csv",
        mime='text/csv',
    )
