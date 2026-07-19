"""都道府県ごとの天気・判定結果を、同じ大きさの正方形タイルのグリッドマップで表示する。

tile_layout.TILE_POSITIONS の相対配置(北海道が最上段、沖縄が最下段、東京が
ほぼ中央)で各都道府県を並べる、いわゆる「タイルグリッドマップ」。実際の
地図タイルは使わないため、隣国が映り込むこともない。
"""

from dog_walk_analysis import judge_walk_suitability
from tile_layout import TILE_POSITIONS
from weather_icons import get_weather_icon

CELL_WIDTH = 50
CELL_HEIGHT = 56
GRID_GAP = 4
BORDER_COLOR = "rgba(30, 30, 30, 0.65)"

_rows = [r for r, _ in TILE_POSITIONS.values()]
_cols = [c for _, c in TILE_POSITIONS.values()]
_MIN_ROW, _MAX_ROW = min(_rows), max(_rows)
_MIN_COL, _MAX_COL = min(_cols), max(_cols)
N_ROWS = _MAX_ROW - _MIN_ROW + 1
N_COLS = _MAX_COL - _MIN_COL + 1

CONTAINER_WIDTH = N_COLS * CELL_WIDTH + (N_COLS - 1) * GRID_GAP
CONTAINER_HEIGHT = N_ROWS * CELL_HEIGHT + (N_ROWS - 1) * GRID_GAP

RECOMMENDED_HEIGHT = CONTAINER_HEIGHT + 40

_GRID_TEMPLATE = (
    f"grid-template-rows: repeat({N_ROWS}, {CELL_HEIGHT}px);"
    f"grid-template-columns: repeat({N_COLS}, {CELL_WIDTH}px);"
    f"gap:{GRID_GAP}px;"
)


def _display_name(name):
    """タイルに表示する県名。「県」「府」「都」の接尾辞だけを外す(北海道はそのまま)。"""
    if name == "北海道":
        return name
    if name.endswith(("県", "府", "都")):
        return name[:-1]
    return name


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_tile_map(data, surface="asphalt"):
    """data: jma_client.fetch_all_prefectures() の結果のリスト。HTML文字列を返す。"""
    cells = []
    for pref in data:
        pos = TILE_POSITIONS.get(pref["name"])
        if pos is None:
            continue
        row, col = pos

        judgement = judge_walk_suitability(pref.get("current_temp"), surface)
        emoji, weather_label = get_weather_icon(pref.get("weather_code"))

        current_temp = pref.get("current_temp")
        temp_text = f"{current_temp:.0f}℃" if current_temp is not None else "--"
        surface_temp = judgement["surface_temp_est"]
        surface_text = f"路面{surface_temp:.0f}℃" if surface_temp is not None else "路面--"

        tooltip = _escape(
            f"{pref['name']}: {weather_label} 現在{temp_text} 推定{surface_text} "
            f"{judgement['label']} - {judgement['message']}"
        )

        cells.append(
            f"""
            <div class="pref-cell" title="{tooltip}" style="
                grid-row:{row - _MIN_ROW + 1}; grid-column:{col - _MIN_COL + 1};
                background:{judgement['color']};
            ">
              <div class="pref-name">{_display_name(pref['name'])}</div>
              <div class="pref-weather">{emoji} {temp_text}</div>
              <div class="pref-surface">{surface_text}</div>
            </div>
            """
        )

    return f"""
    <div style="overflow-x:auto; width:100%;
                font-family:-apple-system, 'Hiragino Sans', 'Yu Gothic', sans-serif;">
      <div style="display:grid; {_GRID_TEMPLATE} width:max-content; margin:0 auto;">
        {''.join(cells)}
      </div>
    </div>
    <style>
      .pref-cell {{
          color:white; border-radius:6px; cursor:default;
          border:2px solid {BORDER_COLOR};
          display:flex; flex-direction:column; align-items:center; justify-content:center;
          box-shadow:0 1px 2px rgba(0,0,0,0.25);
          line-height:1.3; text-align:center;
          box-sizing:border-box;
      }}
      .pref-name {{ font-size:10px; font-weight:bold; opacity:0.95; }}
      .pref-weather {{ font-size:11px; font-weight:bold; white-space:nowrap; }}
      .pref-surface {{ font-size:9px; opacity:0.9; white-space:nowrap; }}
    </style>
    """
