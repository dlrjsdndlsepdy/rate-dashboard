"""
data/rates.csv 를 읽어 docs/index.html (GitHub Pages용 대시보드)을 만듭니다.
외부 패키지는 pandas만 쓰고, 차트는 브라우저에서 Chart.js(CDN)로 그립니다.
"""
import json
import os
import datetime as dt

import pandas as pd

ROOT = os.path.dirname(__file__)
CSV = os.path.join(ROOT, "data", "rates.csv")
OUT = os.path.join(ROOT, "docs", "index.html")

df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date")
payload = {"date": df["date"].dt.strftime("%Y-%m-%d").tolist()}
for c in df.columns:
    if c != "date":
        payload[c] = [None if pd.isna(v) else round(float(v), 3) for v in df[c]]

built = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rates & Spreads Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3;
          --up:#ff6b6b; --down:#4dabf7; --c1:#4dabf7; --c2:#ffa94d; --c3:#69db7c; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--fg); }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:20px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .label { color:var(--muted); font-size:12px; }
  .val { font-size:26px; font-weight:700; margin:4px 0 2px; font-variant-numeric:tabular-nums; }
  .chg { font-size:13px; font-variant-numeric:tabular-nums; }
  .up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--muted); }
  .pct { color:var(--muted); font-size:12px; margin-top:4px; }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
  .panel h2 { font-size:15px; margin:0 0 10px; }
  .ranges { display:flex; gap:6px; margin-bottom:14px; }
  .ranges button { background:var(--card); color:var(--fg); border:1px solid var(--line);
                   border-radius:8px; padding:6px 12px; cursor:pointer; font-size:13px; }
  .ranges button.on { background:var(--c1); border-color:var(--c1); color:#0b1015; font-weight:700; }
  canvas { width:100% !important; height:300px !important; }
  .foot { color:var(--muted); font-size:12px; margin-top:20px; line-height:1.6; }
</style>
</head>
<body>
<div class="wrap">
  <h1>금리 · 스프레드 대시보드</h1>
  <div class="sub">최신 데이터 <b id="asof"></b> · 페이지 생성 __BUILT__</div>

  <div class="cards" id="cards"></div>

  <div class="ranges" id="ranges">
    <button data-d="22">1개월</button><button data-d="66" class="on">3개월</button>
    <button data-d="130">6개월</button><button data-d="260">1년</button><button data-d="0">전체</button>
  </div>

  <div class="panel"><h2>국고채 · 회사채 금리 (%)</h2><canvas id="rates"></canvas></div>
  <div class="panel"><h2>스프레드 (bp)</h2><canvas id="spreads"></canvas></div>

  <div class="foot">
    출처: 한국은행 ECOS 시장금리(일별) — 금융투자협회 최종호가수익률 기준.<br>
    장단기 스프레드 = 국고 10년 − 국고 3년 · 회사채 크레딧 스프레드 = 회사채 AA−(3년) − 국고 3년.<br>
    여전채 = 금융투자협회 채권시가평가기준수익률(평가사 평균) '금융채 II(금융기관채) 무보증 AA−' 3년, 스프레드는 같은 민평 기준 국고채 3년 대비.<br>
    '1년 중 위치'는 최근 약 260영업일 중 오늘 값보다 낮았던 날의 비율입니다.
  </div>
</div>

<script>
const D = __DATA__;
const CARDS = [
  {k:"ktb3",  name:"국고채 3년",        unit:"%"},
  {k:"ktb10", name:"국고채 10년",       unit:"%"},
  {k:"corp_aa", name:"회사채 AA− 3년",  unit:"%"},
  {k:"yeojeon_aa", name:"여전채 AA− 3년 (민평)", unit:"%"},
  {k:"term_spread_bp", name:"장단기 스프레드 (10Y−3Y)", unit:"bp"},
  {k:"corp_spread_bp", name:"회사채 크레딧 스프레드", unit:"bp"},
  {k:"yeojeon_spread_bp", name:"여전채 크레딧 스프레드", unit:"bp"},
];

function lastTwo(arr){ const v = arr.map((x,i)=>[x,i]).filter(p=>p[0]!==null); return [v.at(-1), v.at(-2)]; }
function pctRank(arr, n=260){
  const v = arr.filter(x=>x!==null).slice(-n); const t = v.at(-1);
  return Math.round(100 * v.filter(x=>x<t).length / (v.length-1 || 1));
}

document.getElementById("asof").textContent = D.date.at(-1);
const cardsEl = document.getElementById("cards");
for (const c of CARDS){
  if (!D[c.k]) continue;
  const [cur, prev] = lastTwo(D[c.k]);
  const val = cur[0];
  const diffBp = c.unit === "%" ? (val - prev[0]) * 100 : (val - prev[0]);
  const cls = diffBp > 0.05 ? "up" : diffBp < -0.05 ? "down" : "flat";
  const arrow = cls === "up" ? "▲" : cls === "down" ? "▼" : "–";
  const shown = c.unit === "%" ? val.toFixed(3) + "%" : val.toFixed(1) + "bp";
  cardsEl.insertAdjacentHTML("beforeend", `
    <div class="card"><div class="label">${c.name}</div>
      <div class="val">${shown}</div>
      <div class="chg ${cls}">${arrow} ${Math.abs(diffBp).toFixed(1)}bp (전일 대비)</div>
      <div class="pct">1년 중 위치: ${pctRank(D[c.k])} / 100 <span style="opacity:.7">(0=최저, 100=최고)</span></div></div>`);
}

Chart.defaults.color = "#8b95a3";
Chart.defaults.borderColor = "#2a323d";
function mk(id, series){
  return new Chart(document.getElementById(id), {
    type: "line",
    data: { labels: [], datasets: series.map(s => ({label:s.name, key:s.k, data:[], borderColor:s.color,
            backgroundColor:s.color, borderWidth:2, pointRadius:0, tension:0.15, spanGaps:true})) },
    options: { responsive:true, maintainAspectRatio:false, interaction:{mode:"index", intersect:false},
               plugins:{ legend:{labels:{boxWidth:12}} },
               scales:{ x:{ ticks:{ maxTicksLimit:8 } } } }
  });
}
const charts = [
  mk("rates", [{k:"ktb3",name:"국고 3년",color:"#4dabf7"},{k:"ktb10",name:"국고 10년",color:"#ffa94d"},
               {k:"corp_aa",name:"회사채 AA− 3년",color:"#69db7c"},
               {k:"yeojeon_aa",name:"여전채 AA− 3년",color:"#da77f2"}]),
  mk("spreads", [{k:"term_spread_bp",name:"장단기 (10Y−3Y)",color:"#ffa94d"},
                 {k:"corp_spread_bp",name:"회사채 AA− − 국고 3년",color:"#69db7c"},
                 {k:"yeojeon_spread_bp",name:"여전채 AA− − 국고 3년",color:"#da77f2"}]),
];
function setRange(n){
  const s = n ? Math.max(0, D.date.length - n) : 0;
  for (const ch of charts){
    ch.data.labels = D.date.slice(s);
    for (const ds of ch.data.datasets) ds.data = (D[ds.key] || []).slice(s);
    ch.update();
  }
}
document.querySelectorAll("#ranges button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#ranges button").forEach(x => x.classList.remove("on"));
  b.classList.add("on"); setRange(+b.dataset.d);
});
setRange(66);
</script>
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__BUILT__", built))
print(f"대시보드 생성: {OUT} (최신 {payload['date'][-1]})")
