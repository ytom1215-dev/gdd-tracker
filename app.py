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
st.title("🌡️ 積算温度 到達日推定アプリ (自動取得版)")

# 1. APIからのデータ読み込み（CSV読み込みから差し替え）
@st.cache_data(ttl=3600)  # 1時間ごとにキャッシュを更新してAPI負荷を軽減
def load_api_data(year):
    # 鹿屋市付近の座標
    lat, lon = 31.3783, 130.8522 
    start_str = f"{year}-01-01"
    end_str = f"{year}-12-31" # 年末まで取得しておく
    today_str = date.today().strftime('%Y-%m-%d')

    # 実績データの取得 (年初から今日まで)
    res_url = "https://archive-api.open-meteo.com/v1/archive"
    res_params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": today_str,
        "daily": "temperature_2m_mean", "timezone": "Asia/Tokyo"
    }
    
    # 平年値データの取得 (年間)
    cli_url = "https://climate-api.open-meteo.com/v1/climate"
    cli_params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_str, "end_date": end_str,
        "models": "best_match", "daily": "temperature_2m_mean"
    }

    try:
        # APIリクエスト
        res_data = requests.get(res_url, params=res_params).json()
        cli_data = requests.get(cli_url, params=cli_params).json()

        # DataFrame化
        df_act = pd.DataFrame({
            "年月日": pd.to_datetime(res_data["daily"]["time"]),
            "平均気温(℃)": res_data["daily"]["temperature_2m_mean"]
        })
        df_cli = pd.DataFrame({
            "年月日": pd.to_datetime(cli_data["daily"]["time"]),
            "平年値平均気温(℃)": cli_data["daily"]["temperature_2m_mean"]
        })

        # 結合（平年値をベースに、実績データを左結合。未来の実績はNaNになる）
        df = pd.merge(df_cli, df_act, on="年月日", how="left")
        return df

    except Exception as e:
        st.error(f"データ取得に失敗しました: {e}")
        return pd.DataFrame()

# 今年のデータを自動取得
current_year = datetime.now().year
df = load_api_data(current_year)

if not df.empty:
    # 2. 設定（サイドバー）
    st.sidebar.header("⚙️ 設定パネル")
    min_date_val = df['年月日'].min().date()
    max_date_val = df['年月日'].max().date()
    real_today = datetime.now().date()

    start_date = st.sidebar.date_input("📅 積算開始日", value=min_date_val, min_value=min_date_val, max_value=max_date_val)
    today_date = st.sidebar.date_input("📅 現在の日付 (これ以降は平年値)", value=real_today)
    
    # ▼新規追加：基準温度（0にすれば単純な積算温度になります）
    base_temp = st.sidebar.number_input("🌱 基準温度 (℃)", value=0.0, step=0.5, help="この温度を下回る日は0として計算します")
    target_temp = st.sidebar.number_input("🌡️ 目標積算温度 (℃)", value=1500, step=100)

    # 3. 計算と表示
    if start_date:
        mask = df['年月日'].dt.date >= start_date
        calc_df = df[mask].copy()
        
        if calc_df.empty:
            st.error("選択された開始日以降のデータがありません。")
        else:
            # 気温の適用ルール（作成されたロジックを活用＋基準温度を考慮）
            def get_effective_temp(row):
                if row['年月日'].date() < today_date:
                    # APIから今日の実績がまだ来ていない場合は NaN になるため、その場合は平年値でカバー
                    temp = row['平均気温(℃)'] if not pd.isna(row['平均気温(℃)']) else row['平年値平均気温(℃)']
                else:
                    temp = row['平年値平均気温(℃)']
                
                # 基準温度を差し引き、マイナスになった場合は0にする
                return max(0, temp - base_temp)

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
            with st.expander("計算データの詳細を確認"):
                # 小数点以下を整理して見やすく表示
                display_df = calc_df[['年月日', '平均気温(℃)', '平年値平均気温(℃)', '適用気温', '積算温度']].copy()
                st.dataframe(display_df.style.format({
                    '平均気温(℃)': '{:.1f}',
                    '平年値平均気温(℃)': '{:.1f}',
                    '適用気温': '{:.1f}',
                    '積算温度': '{:.1f}'
                }))