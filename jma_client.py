"""気象庁(JMA)の非公式JSON APIから都道府県ごとの天気予報を取得する。

エンドポイント: https://www.jma.go.jp/bosai/forecast/data/forecast/{office_code}.json
本APIは気象庁が公式にドキュメント化しているものではないが、気象庁サイト自体が
内部で利用しており、天気予報を扱う多くの個人・OSSプロジェクトで広く使われている。
"""

import concurrent.futures

import requests
import streamlit as st

from prefectures import PREFECTURES

FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{office_code}.json"
AMEDAS_LATEST_TIME_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
AMEDAS_MAP_URL = "https://www.jma.go.jp/bosai/amedas/data/map/{timestamp}.json"
REQUEST_TIMEOUT = 10
MAX_WORKERS = 10
HEADERS = {"User-Agent": "dog-walk-alarm/1.0 (personal weather app)"}


def fetch_forecast(office_code):
    """指定した予報区コードの生の予報JSONを取得する。失敗時はNoneを返す。"""
    url = FORECAST_URL.format(office_code=office_code)
    try:
        res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return res.json()
    except (requests.RequestException, ValueError):
        return None


def fetch_amedas_current():
    """全国のアメダス観測点の現在気温を取得する。

    戻り値は {観測点コード: 気温(℃)} の辞書。取得失敗時は空辞書を返す。
    """
    try:
        res = requests.get(AMEDAS_LATEST_TIME_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        latest_time = res.text.strip()
        timestamp = (
            latest_time[0:4] + latest_time[5:7] + latest_time[8:10]
            + latest_time[11:13] + latest_time[14:16] + latest_time[17:19]
        )
        res = requests.get(
            AMEDAS_MAP_URL.format(timestamp=timestamp), headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        res.raise_for_status()
        stations = res.json()
    except (requests.RequestException, ValueError, IndexError):
        return {}

    return {
        code: obs["temp"][0]
        for code, obs in stations.items()
        if obs.get("temp") and obs["temp"][0] is not None
    }


def _first_non_empty(values):
    for v in values:
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def parse_forecast(raw_json):
    """予報JSONから天気コード・天気概況・本日の最高/最低気温を抽出する。

    温度系列は [本日の最高気温, 本日の最低気温(既に確定済みの場合あり),
    明日の最低気温, 明日の最高気温] という4要素配列で提供されることが多いため、
    先頭2要素を本日の最高・最低気温として扱う簡易的な解釈を採用している。
    """
    result = {
        "weather_code": None,
        "weather_text": None,
        "temp_max": None,
        "temp_min": None,
        "amedas_code": None,
    }
    if not raw_json:
        return result

    try:
        time_series = raw_json[0]["timeSeries"]
    except (KeyError, IndexError, TypeError):
        return result

    for series in time_series:
        areas = series.get("areas", [])
        if not areas:
            continue

        if "weatherCodes" in areas[0] and result["weather_code"] is None:
            codes = areas[0]["weatherCodes"]
            if codes:
                result["weather_code"] = codes[0]
            weathers = areas[0].get("weathers")
            if weathers:
                result["weather_text"] = weathers[0].replace("　", " ")

        if "temps" in areas[0] and result["temp_max"] is None:
            result["amedas_code"] = areas[0]["area"]["code"]
            temps = areas[0]["temps"]
            temp_max = _first_non_empty(temps[0:1])
            temp_min = _first_non_empty(temps[1:2])
            # 発表時刻によっては「本日の最低気温」が既に確定済みで取得できず、
            # 代わりに最高気温と同じ値が入ってくることがある。その場合は
            # 紛らわしいので取得不可(None)として扱う。
            if temp_min is not None and temp_max is not None and temp_min == temp_max:
                temp_min = None
            if temp_max is not None and temp_min is not None and temp_min > temp_max:
                temp_max, temp_min = temp_min, temp_max
            result["temp_max"] = temp_max
            result["temp_min"] = temp_min

    return result


def _fetch_one(pref):
    raw = fetch_forecast(pref["office_code"])
    parsed = parse_forecast(raw)
    return {**pref, **parsed, "fetch_ok": raw is not None}


@st.cache_data(ttl=600, show_spinner="気象庁から全国の天気を取得中...")
def fetch_all_prefectures():
    """47都道府県分の予報+現在気温を並列取得する。戻り値は prefectures.PREFECTURES と同じ順序。"""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_name = {
            executor.submit(_fetch_one, pref): pref["name"] for pref in PREFECTURES
        }
        for future in concurrent.futures.as_completed(future_to_name):
            data = future.result()
            results[data["name"]] = data

    amedas = fetch_amedas_current()
    for data in results.values():
        data["current_temp"] = amedas.get(data["amedas_code"])
        data["amedas_ok"] = bool(amedas)

    return [results[pref["name"]] for pref in PREFECTURES]
