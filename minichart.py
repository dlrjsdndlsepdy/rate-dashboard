"""
해석 페이지용 작은 그래프 도우미 (한국·미국 해석 페이지 공용).

사용법
  spec = chart(frame_name, df, [col, ...], names)   # 신호 하나에 붙일 그래프 정의
  html = canvas(spec)                                # 그래프 + 설명 한 줄 HTML
  script(frames)                                     # 페이지 맨 아래 1번: 데이터 + Chart.js 그리기 코드
"""
import json
import math

import pandas as pd

SHOW_N = 60      # 그래프에 보여줄 영업일 수
AVG_N = 260      # 평균선 기준 (1년)
_counter = [0]


def chart(frame: str, df: pd.DataFrame, cols, names: dict) -> dict:
    """names: {col: (표시이름, 단위)}  단위: '%', 'bp', '원'"""
    cols = [c for c in cols if c in df.columns and df[c].notna().any()]
    if not cols:
        return {}
    cap = []
    for c in cols:
        s = df[c].dropna()
        if len(s) < 2:
            continue
        name, unit = names.get(c, (c, "%"))
        now, ago = float(s.iloc[-1]), float(s.iloc[-min(SHOW_N, len(s))])
        avg = float(s.iloc[-AVG_N:].mean())
        cap.append(f"{name} 오늘 {_fmt(now, unit)} · {SHOW_N}영업일 전 {_fmt(ago, unit)} · 1년 평균 {_fmt(avg, unit)}")
    return {"frame": frame, "cols": cols,
            "labels": [names.get(c, (c, ""))[0] for c in cols],
            "units": [names.get(c, ("", "%"))[1] for c in cols],
            "caption": " / ".join(cap)}


def _fmt(v, unit):
    if v is None or math.isnan(v):
        return "n/a"
    return f"{v:.2f}%" if unit == "%" else (f"{v:,.1f}원" if unit == "원" else f"{v:.1f}bp")


def canvas(spec: dict, height: int = 170) -> str:
    if not spec:
        return ""
    _counter[0] += 1
    cid = f"mc{_counter[0]}"
    attrs = (f'data-frame="{spec["frame"]}" data-cols="{",".join(spec["cols"])}" '
             f'data-labels="{"|".join(spec["labels"])}" data-units="{",".join(spec["units"])}"')
    return (f'<div class="mc"><div style="position:relative;height:{height}px">'
            f'<canvas id="{cid}" {attrs}></canvas></div>'
            f'<div class="mccap">{spec["caption"]}</div></div>')


def payload(frames: dict) -> dict:
    """frames: {이름: DataFrame(날짜 인덱스)} → 최근 1년치만 JSON으로."""
    out = {}
    for k, df in frames.items():
        d = df.iloc[-AVG_N:]
        p = {"date": d.index.strftime("%Y-%m-%d").tolist()}
        for c in d.columns:
            if pd.api.types.is_numeric_dtype(d[c]):
                p[c] = [None if pd.isna(v) else round(float(v), 4) for v in d[c]]
        out[k] = p
    return out


CSS = """
  .mc { margin:8px 0 14px; background:#141a21; border:1px solid var(--line); border-radius:10px; padding:10px 12px 8px; }
  .mccap { color:var(--muted); font-size:12px; margin-top:6px; line-height:1.5; }
"""


def script(frames: dict) -> str:
    data = json.dumps(payload(frames), ensure_ascii=False)
    js = """<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const MC = __DATA__;
const MCOL = ["#4dabf7","#ffa94d","#69db7c","#da77f2"];
Chart.defaults.color = "#8b95a3"; Chart.defaults.borderColor = "#2a323d"; Chart.defaults.font.size = 11;
document.querySelectorAll("canvas[data-cols]").forEach(cv => {
  const F = MC[cv.dataset.frame]; if (!F) return;
  const cols = cv.dataset.cols.split(","), labels = cv.dataset.labels.split("|"), units = cv.dataset.units.split(",");
  const N = """ + str(SHOW_N) + """, s = Math.max(0, F.date.length - N);
  const mixed = new Set(units.map(u => u === "%" ? "%" : "x")).size > 1;
  const ds = [];
  cols.forEach((c, i) => {
    const full = F[c] || []; const v = full.slice(s);
    const axis = mixed && units[i] !== "%" ? "y1" : "y";
    ds.push({ label: labels[i] + (mixed ? (units[i] === "%" ? " (%, 왼쪽)" : ` (${units[i]}, 오른쪽)`) : ""),
      data: v, borderColor: MCOL[i], backgroundColor: MCOL[i], borderWidth: 2, tension: 0.15, spanGaps: true, yAxisID: axis,
      pointRadius: v.map((_, j) => j === v.length - 1 ? 4 : 0) });
    if (cols.length === 1) {   // 단일 지표면 1년 평균 점선
      const nn = full.filter(x => x !== null); const avg = nn.reduce((a, b) => a + b, 0) / (nn.length || 1);
      ds.push({ label: "1년 평균", data: v.map(() => avg), borderColor: "#8b95a3", borderDash: [4, 4], borderWidth: 1, pointRadius: 0 });
    }
  });
  const scales = { x: { ticks: { maxTicksLimit: 5 } }, y: { position: "left" } };
  if (mixed) scales.y1 = { position: "right", grid: { drawOnChartArea: false } };
  new Chart(cv, { type: "line", data: { labels: F.date.slice(s), datasets: ds },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { boxWidth: 10 } } }, scales } });
});
</script>"""
    return js.replace("__DATA__", data)
