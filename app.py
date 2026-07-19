"""お犬様散歩アラーム — 気象庁データを基に犬の散歩に適した気温かをチェックするWebアプリ。"""

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dog_walk_analysis import LEVEL_STYLE, SURFACE_LABELS, judge_walk_suitability
from jma_client import fetch_all_prefectures
from tile_map_view import RECOMMENDED_HEIGHT, render_tile_map
from weather_icons import get_weather_icon

st.set_page_config(
    page_title="お犬様散歩アラーム",
    page_icon="🐶",
    layout="wide",
)

st.title("🐶 お犬様散歩アラーム")
st.caption("気象庁の観測・予報データをもとに、全国の犬の散歩に適した気温かどうかをチェックします。")

with st.sidebar:
    st.header("設定")
    surface = st.radio(
        "地面タイプ",
        options=["asphalt", "soil"],
        format_func=lambda s: SURFACE_LABELS[s],
        help="散歩コースの主な路面素材を選んでください。路面温度の推定に使用します。",
    )
    if st.button("🔄 最新データに更新"):
        fetch_all_prefectures.clear()
        st.rerun()
    st.caption("気象庁のアメダス現在気温・天気予報を10分キャッシュして表示しています。")
    st.caption(
        "※ 路面温度は現在気温からの概算(目安)です。実際は日射・風・時間帯・"
        "路面の状態によって大きく変わります。"
    )

data = fetch_all_prefectures()

rows = []
for pref in data:
    judgement = judge_walk_suitability(pref.get("current_temp"), surface)
    emoji, weather_label = get_weather_icon(pref.get("weather_code"))
    rows.append(
        {
            "都道府県": pref["name"],
            "天気": f"{emoji} {weather_label}",
            "現在気温(℃)": pref.get("current_temp"),
            "推定路面温度(℃)": judgement["surface_temp_est"],
            "判定": f"{judgement['dog_emoji']} {judgement['label']}",
            "レベル": judgement["level"],
            "アドバイス": judgement["message"],
            "取得成功": pref.get("fetch_ok", False),
        }
    )
df = pd.DataFrame(rows)

failed = (~df["取得成功"]).sum()
if failed:
    st.warning(f"{failed}件の都道府県で天気データの取得に失敗しました。時間をおいて更新をお試しください。")
if data and not any(p.get("current_temp") is not None for p in data):
    st.warning("現在気温(アメダス)データを取得できませんでした。時間をおいて更新をお試しください。")

st.subheader("全国サマリー")
summary_cols = st.columns(4)
level_order = ["safe", "caution", "danger", "cold"]
for col, level in zip(summary_cols, level_order):
    style = LEVEL_STYLE[level]
    count = (df["レベル"] == level).sum()
    col.metric(f"{style['dog_emoji']} {style['label']}", f"{count} 県")

st.subheader("🗺️ 全国マップ(タイルグリッド)")
st.caption(
    "都道府県を同じ大きさのタイルでグリッド状に配置したデフォルメ地図です"
    "(北海道が上、沖縄が下、東京がほぼ中央)。各タイルに現在気温と"
    "推定路面温度を併記しています(色は散歩適性の判定)。"
)
tile_html = render_tile_map(data, surface)
components.html(tile_html, height=RECOMMENDED_HEIGHT, scrolling=True)

st.subheader("🌡️ 現在の気温ランキング")
st.caption("現在気温が高い順に並べています。判定の🐶マークで散歩の可否がひと目でわかります。")
ranking_df = df.sort_values("現在気温(℃)", ascending=False, na_position="last").reset_index(drop=True)
ranking_df.insert(
    0,
    "順位",
    [str(i + 1) if pd.notna(t) else "-" for i, t in enumerate(ranking_df["現在気温(℃)"])],
)
display_df = ranking_df.drop(columns=["レベル", "取得成功"]).copy()
for col in ["現在気温(℃)", "推定路面温度(℃)"]:
    display_df[col] = display_df[col].apply(lambda v: "--" if pd.isna(v) else v)
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)
