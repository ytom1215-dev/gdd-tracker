import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import warnings

# グラフの日本語文字化け対策
warnings.filterwarnings('ignore')
try:
    plt.rcParams['font.family'] = 'Meiryo' 
except:
    pass

st.set_page_config(page_title="積算温度 到達日推定アプリ", layout="wide")
st.title("🌡️ 積算温度 到達日推定アプリ (安定・CSV版)")

# 1. データの読み込み
@st.cache_data
def load_data():
    try:
        # 見えない記号(BOM)を消すために utf-8-sig を使用
        df = pd.read_csv("data (1).csv", encoding="utf-8-sig")
    except:
        df = pd.read_csv("data (1).csv", encoding="cp932")
    df.columns = df.columns.str.strip()
    df['年月日'] = pd.to_datetime(df['年月日'])
    return df

try:
    df = load_data()
except FileNotFoundError:
    st.error("⚠️ 'data (1).csv' ファイルが見つかりません。アプリと同じフォルダにアップロードしてください。")
    st.stop()

# 2. 設定（サイドバー）
st.sidebar.header("⚙️ 設定パネル")
min_date_val = df['年月日'].min().date()
max_date_val = df['年月日'].max().date()
real_today = datetime.now().date()

start_date = st.sidebar.date_input("📅 積算開始日", value=min_date_val, min_value=min_date_val, max_value=max_date_val)
today_date = st.sidebar.date_input("📅 現在の日付 (これ以降は平年値)", value=real_today)

# ▼ API版で作った便利な機能をここだけ移植
base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5, help="この温度を下回る日は0として計算します")
target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)

# 3. 計算と表示
if start_date:
    mask = df['年月日'].dt.date >= start_date
    calc_df = df[mask].copy()
    
    if calc_df.empty:
        st.error("選択された開始日以降のデータがありません。")
    else:
        # 気温の適用ルール
        def get_effective_temp(row):
            if row['年月日'].date() < today_date:
                val = row['平均気温(℃)'] if not pd.isna(row['平均気温(℃)']) else row['平年値平均気温(℃)']
            else:
                val = row['平年値平均気温(℃)']
            
            # 基準温度を差し引く
            return max(0, val - base_temp)

        calc_df['適用気温'] = calc_df.apply(get_effective_temp, axis=1)
        calc_df['積算温度'] = calc_df['適用気温'].cumsum()

        reach_df = calc_df[calc_df['積算温度'] >= target_temp]
        
        st.markdown("---")
        if not reach_df.empty:
            reach_date = reach_df.iloc[0]['年月日'].date()
            st.success(f"### 🎉 目標の積算温度 **{target_temp}℃** に到達する推定日は **{reach_date}** です！")
        else:
            st.warning(f"⚠️ データ期間内に積算温度 {target_temp}℃ に到達しませんでした。")

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

        # データ詳細
        with st.expander("📝 計算データの詳細を確認"):
            display_df = calc_df[['年月日', '平均気温(℃)', '平年値平均気温(℃)', '適用気温', '積算温度']].copy()
            st.dataframe(display_df.style.format({
                '平均気温(℃)': '{:.1f}',
                '平年値平均気温(℃)': '{:.1f}',
                '適用気温': '{:.1f}',
                '積算温度': '{:.1f}'
            }))
