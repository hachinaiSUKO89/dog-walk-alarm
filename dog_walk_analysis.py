"""ルールベースの「AI分析」: 気温から地面(路面)温度を推定し、犬の散歩適性を判定する。

路面温度の推定は、気温と路面温度の関係としてよく知られる目安値
(気温25℃→アスファルト路面52℃、30℃→60℃、35℃→65℃ 前後)を基準点とした
線形補間による概算であり、厳密な物理計算ではない点に留意すること。
これは「直射日光が当たり続けている場合」の目安のため、実際の天気
(曇り・雨・雪)と時間帯(夜間は日射がない)によって日射による上乗せ分を
補正している。風・路面の色や状態によっても実際の値は大きく変動する。
"""

from datetime import datetime, timedelta, timezone

_JST = timezone(timedelta(hours=9))

# (気温, 推定路面温度) の基準点。直射日光下を想定した高めの値。
# 土・芝は保熱しにくいため上昇幅を小さく設定している。
_ASPHALT_POINTS = [
    (0, 5), (10, 18), (15, 28), (20, 38), (25, 52), (30, 60), (35, 65), (40, 71),
]
_SOIL_POINTS = [
    (0, 2), (10, 14), (15, 20), (20, 27), (25, 33), (30, 40), (35, 45), (40, 50),
]

# 天気(気象庁天気コードの先頭桁)による日射補正係数。
# 曇り・雨・雪の日は直射日光が弱い/無いため、気温から上乗せされる分を
# この係数で割り引く。1.0=快晴と同等、0に近いほど日射の影響が小さい。
_SUN_FACTOR_BY_PREFIX = {
    "1": 1.0,   # 晴れ系
    "2": 0.55,  # 曇り系
    "3": 0.25,  # 雨系
    "4": 0.2,   # 雪系
}
_DEFAULT_SUN_FACTOR = 0.7  # 天気コードが不明な場合の中間的な係数

# 時刻(0〜24時, JST)による日射補正係数。日中にピークを迎え、日の出前・
# 日没後はほぼ0(直射日光がないため路面温度は気温に近づく)になる。
_TIME_FACTOR_POINTS = [
    (0, 0.05), (5, 0.05), (7, 0.3), (9, 0.7), (12, 1.0),
    (14, 1.0), (16, 0.7), (18, 0.35), (20, 0.1), (24, 0.05),
]

SURFACE_LABELS = {"asphalt": "アスファルト", "soil": "土・芝"}


def _interpolate(temp, points):
    if temp <= points[0][0]:
        x0, y0 = points[0]
        x1, y1 = points[1]
    elif temp >= points[-1][0]:
        x0, y0 = points[-2]
        x1, y1 = points[-1]
    else:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= temp <= x1:
                break
    ratio = (temp - x0) / (x1 - x0)
    return y0 + ratio * (y1 - y0)


def sun_factor(weather_code):
    """天気コードから日射補正係数(0〜1)を返す。"""
    if weather_code is None:
        return _DEFAULT_SUN_FACTOR
    code = str(weather_code)
    return _SUN_FACTOR_BY_PREFIX.get(code[:1], _DEFAULT_SUN_FACTOR)


def time_factor(now=None):
    """現在時刻(JST)から日射補正係数(0〜1)を返す。"""
    if now is None:
        now = datetime.now(_JST)
    hour = now.hour + now.minute / 60
    return _interpolate(hour, _TIME_FACTOR_POINTS)


def estimate_surface_temp(air_temp, surface="asphalt", weather_code=None, now=None):
    """気温(℃)・天気・時刻から地面表面温度の概算値(℃)を返す。

    直射日光下を想定した基準カーブに対し、天気と時間帯による日射補正係数を
    かけた上で気温に上乗せする(曇り・雨の日や夜間は上乗せ分を割り引く)。
    """
    if air_temp is None:
        return None
    points = _ASPHALT_POINTS if surface == "asphalt" else _SOIL_POINTS
    full_sun_temp = _interpolate(air_temp, points)
    boost = (full_sun_temp - air_temp) * sun_factor(weather_code) * time_factor(now)
    return round(air_temp + boost, 1)


LEVEL_STYLE = {
    "safe": {"emoji": "🟢", "dog_emoji": "🐶😊", "label": "適温", "color": "#2e7d32"},
    "caution": {"emoji": "🟡", "dog_emoji": "🐶😓", "label": "注意", "color": "#f9a825"},
    "danger": {"emoji": "🔴", "dog_emoji": "🐶🥵", "label": "危険", "color": "#c62828"},
    "cold": {"emoji": "🔵", "dog_emoji": "🐶🥶", "label": "防寒注意", "color": "#1565c0"},
    "unknown": {"emoji": "⚪", "dog_emoji": "🐶❓", "label": "データなし", "color": "#9e9e9e"},
}


def judge_walk_suitability(air_temp, surface="asphalt", weather_code=None, now=None):
    """気温・地面タイプ・天気・時刻から散歩適性を判定する。

    戻り値: {"level", "emoji", "label", "color", "message", "surface_temp_est"}
    """
    if air_temp is None:
        style = LEVEL_STYLE["unknown"]
        return {
            "level": "unknown",
            "emoji": style["emoji"],
            "dog_emoji": style["dog_emoji"],
            "label": style["label"],
            "color": style["color"],
            "message": "気温データを取得できませんでした。",
            "surface_temp_est": None,
        }

    surface_temp = estimate_surface_temp(air_temp, surface, weather_code, now)
    surface_label = SURFACE_LABELS[surface]

    if air_temp < 0:
        level = "cold"
        message = (
            f"気温{air_temp:.0f}℃と厳寒です。凍結路面にも注意し、"
            "短時間の散歩・防寒着の着用を検討しましょう。"
        )
    elif air_temp < 5:
        level = "cold"
        message = (
            f"気温{air_temp:.0f}℃で肌寒いです。小型犬・短毛種は防寒着を、"
            "散歩時間は短めにするのがおすすめです。"
        )
    elif surface == "asphalt" and surface_temp >= 60:
        level = "danger"
        message = (
            f"路面温度は推定約{surface_temp:.0f}℃。肉球やけどの危険が高いため、"
            "日中の散歩は避け、早朝・夜間の涼しい時間帯にしましょう。"
        )
    elif air_temp >= 32 or (surface == "asphalt" and surface_temp >= 50):
        level = "danger"
        message = (
            f"気温{air_temp:.0f}℃・推定路面温度約{surface_temp:.0f}℃。"
            "熱中症・やけどのリスクが高い状況です。散歩は控えるか早朝夜間のみに。"
        )
    elif air_temp >= 28 or (surface == "asphalt" and surface_temp >= 40):
        level = "caution"
        message = (
            f"気温{air_temp:.0f}℃・推定路面温度約{surface_temp:.0f}℃。"
            f"{surface_label}は熱がこもりやすいので、日陰や涼しい時間帯を選びましょう。"
        )
    elif air_temp <= 28:
        level = "safe"
        message = (
            f"気温{air_temp:.0f}℃・推定路面温度約{surface_temp:.0f}℃で、"
            "散歩に適した過ごしやすいコンディションです。"
        )
    else:
        level = "caution"
        message = "念のため路面温度や犬の様子を確認しながら散歩しましょう。"

    style = LEVEL_STYLE[level]
    return {
        "level": level,
        "emoji": style["emoji"],
        "dog_emoji": style["dog_emoji"],
        "label": style["label"],
        "color": style["color"],
        "message": message,
        "surface_temp_est": surface_temp,
    }
