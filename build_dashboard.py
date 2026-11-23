"""
data/rates.csv 를 읽어 docs/index.html (GitHub Pages용 대시보드)을 만듭니다.
외부 패키지는 pandas만 쓰고, 차트는 브라우저에서 Chart.js(CDN)로 그립니다.
업권별 탭: 공통 / 캐피탈 / 보험 / 은행
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
          --up:#ff6b6b; --down:#4dabf7; --accent:#4dabf7; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--fg); }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:18px; }
  .tabs { display:flex; gap:4px; border-bottom:1px solid var(--line); margin-bottom:16px; flex-wrap:wrap; }
  .tabs button { background:none; border:none; color:var(--muted); font-size:15px; padding:10px 16px;
                 cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
  .tabs button.on { color:var(--fg); border-bottom-color:var(--accent); font-weight:700; }
  .desc { color:var(--muted); font-size:13px; margin:0 0 14px; line-height:1.6; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .label { color:var(--muted); font-size:12px; }
  .val { font-size:26px; font-weight:700; margin:4px 0 2px; font-variant-numeric:tabular-nums; }
  .chg { font-size:13px; font-variant-numeric:tabular-nums; }
  .up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--muted); }
  .pct { color:var(--muted); font-size:12px; margin-top:6px; }
  .bar { height:4px; background:var(--line); border-radius:2px; margin-top:4px; position:relative; }
  .bar i { position:absolute; top:-3px; width:4px; height:10px; border-radius:2px; background:var(--fg); }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
  .panel h2 { font-size:15px; margin:0 0 10px; }
  .ranges { display:flex; gap:6px; margin-bottom:14px; }
  .ranges button { background:var(--card); color:var(--fg); border:1px solid var(--line);
                   border-radius:8px; padding:6px 12px; cursor:pointer; font-size:13px; }
  .ranges button.on { background:var(--accent); border-color:var(--accent); color:#0b1015; font-weight:700; }
  .chartbox { position:relative; height:300px; }
  .foot { color:var(--muted); font-size:12px; margin-top:20px; line-height:1.7; }
</style>
</head>
<body>
<div class="wrap">
  <h1>금리 · 스프레드 대시보드</h1>
  <div class="sub">최신 데이터 <b id="asof"></b> · 페이지 생성 __BUILT__</div>

  <div class="tabs" id="tabs"></div>
  <p class="desc" id="desc"></p>
  <div class="cards" id="cards"></div>

  <div class="ranges" id="ranges">
    <button data-d="22">1개월</button><button data-d="66" class="on">3개월</button>
    <button data-d="130">6개월</button><button data-d="260">1년</button><button data-d="0">전체</button>
  </div>

  <div class="panel"><h2 id="t1"></h2><div class="chartbox"><canvas id="c1"></canvas></div></div>
  <div class="panel"><h2 id="t2"></h2><div class="chartbox"><canvas id="c2"></canvas></div></div>

  <div class="foot">
    <b>출처</b> · 한국은행 ECOS 시장금리(일별, 금융투자협회 최종호가수익률 기준): 국고채 3·10·30년, 회사채 AA− 3년, CD·CP 91일.<br>
    금융투자협회 채권시가평가기준수익률(평가사 평균, 민평): 여전채 = '금융채 II(금융기관채) 무보증' AA−·A+ 3년. 여전채 스프레드는 같은 민평 기준 국고 3년 대비.<br>
    <b>정의</b> · 장단기 = 국고 10Y−3Y · 초장기 = 국고 30Y−10Y · 회사채 스프레드 = 회사채 AA−−국고 3Y ·
    등급 스프레드 = 여전채 A+ − AA− · CP−CD = CP 91일 − CD 91일.<br>
    '1년 중 위치'는 최근 약 260영업일 중 오늘 값보다 낮았던 날의 비율(0=1년 최저, 100=1년 최고)입니다.
  </div>
</div>

<script>
const D = __DATA__;

const COLORS = ["#4dabf7","#ffa94d","#69db7c","#da77f2","#ff8787","#ffd43b"];
const TABS = [
  { id:"common", name:"공통",
    desc:"국고채 커브와 일반 회사채 크레딧. 모든 업권의 출발점이에요.",
    cards:[["ktb3","국고채 3년","%"],["ktb10","국고채 10년","%"],["corp_aa","회사채 AA− 3년","%"],
           ["term_spread_bp","장단기 스프레드 (10Y−3Y)","bp"],["corp_spread_bp","회사채 크레딧 스프레드","bp"]],
    c1:["국고채 · 회사채 금리 (%)", [["ktb3","국고 3년"],["ktb10","국고 10년"],["corp_aa","회사채 AA− 3년"]]],
    c2:["스프레드 (bp)", [["term_spread_bp","장단기 (10Y−3Y)"],["corp_spread_bp","회사채 AA− − 국고 3년"]]] },
  { id:"capital", name:"캐피탈",
    desc:"여전채 조달금리와 등급 간 격차(대형 AA급 vs 중소형 A급), 단기 조달시장(CP) 온도.",
    cards:[["yeojeon_aa","여전채 AA− 3년","%"],["yeojeon_a_plus","여전채 A+ 3년","%"],
           ["yeojeon_spread_bp","여전채 AA− 크레딧 스프레드","bp"],["yeojeon_grade_bp","등급 스프레드 (A+ − AA−)","bp"],
           ["cp91","CP 91일","%"],["cp_cd_spread_bp","CP − CD 스프레드","bp"]],
    c1:["여전채 · 단기 조달금리 (%)", [["yeojeon_aa","여전채 AA− 3년"],["yeojeon_a_plus","여전채 A+ 3년"],["cp91","CP 91일"],["cd91","CD 91일"]]],
    c2:["캐피탈 스프레드 (bp)", [["yeojeon_spread_bp","여전채 AA− − 국고 3년"],["yeojeon_grade_bp","A+ − AA−"],["cp_cd_spread_bp","CP − CD"]]] },
  { id:"insurance", name:"보험",
    desc:"보험사 ALM·K-ICS의 핵심인 초장기 구간. 10-30 스프레드가 낮거나 역전이면 초장기채 수요가 강하다는 신호예요.",
    cards:[["ktb10","국고채 10년","%"],["ktb30","국고채 30년","%"],["ultra_spread_bp","초장기 스프레드 (30Y−10Y)","bp"],
           ["term_spread_bp","장단기 스프레드 (10Y−3Y)","bp"]],
    c1:["장기 · 초장기 국고채 (%)", [["ktb3","국고 3년"],["ktb10","국고 10년"],["ktb30","국고 30년"]]],
    c2:["커브 기울기 (bp)", [["ultra_spread_bp","30Y − 10Y"],["term_spread_bp","10Y − 3Y"]]] },
  { id:"bank", name:"은행",
    desc:"은행 단기 조달·대출 기준금리인 CD, 그리고 단기 자금시장 스트레스(CP−CD).",
    cards:[["cd91","CD 91일","%"],["cp91","CP 91일","%"],["cp_cd_spread_bp","CP − CD 스프레드","bp"],["ktb3","국고채 3년","%"]],
    c1:["단기 금리 (%)", [["cd91","CD 91일"],["cp91","CP 91일"],["ktb3","국고 3년"]]],
    c2:["단기 스프레드 (bp)", [["cp_cd_spread_bp","CP − CD"]]] },
];

function lastTwo(arr){ const v = arr.map((x,i)=>[x,i]).filter(p=>p[0]!==null); return [v.at(-1), v.at(-2)]; }
function pctRank(arr, n=260){
  const v = arr.filter(x=>x!==null).slice(-n); const t = v.at(-1);
  return Math.round(100 * v.filter(x=>x<t).length / (v.length-1 || 1));
}

document.getElementById("asof").textContent = D.date.at(-1);
Chart.defaults.color = "#8b95a3";
Chart.defaults.borderColor = "#2a323d";
function mk(id){
  return new Chart(document.getElementById(id), {
    type:"line", data:{labels:[], datasets:[]},
    options:{ responsive:true, maintainAspectRatio:false, interaction:{mode:"index", intersect:false},
              plugins:{ legend:{labels:{boxWidth:12}} }, scales:{ x:{ ticks:{ maxTicksLimit:8 } } } }
  });
}
const ch1 = mk("c1"), ch2 = mk("c2");
let cur = TABS[0], range = 66;

function renderCards(){
  const el = document.getElementById("cards"); el.innerHTML = "";
  for (const [k,name,unit] of cur.cards){
    if (!D[k] || D[k].every(x=>x===null)) continue;
    const [c, p] = lastTwo(D[k]); const val = c[0];
    const diffBp = unit === "%" ? (val - p[0]) * 100 : (val - p[0]);
    const cls = diffBp > 0.05 ? "up" : diffBp < -0.05 ? "down" : "flat";
    const arrow = cls === "up" ? "▲" : cls === "down" ? "▼" : "–";
    const shown = unit === "%" ? val.toFixed(3) + "%" : val.toFixed(1) + "bp";
    const pr = pctRank(D[k]);
    el.insertAdjacentHTML("beforeend", `
      <div class="card"><div class="label">${name}</div>
        <div class="val">${shown}</div>
        <div class="chg ${cls}">${arrow} ${Math.abs(diffBp).toFixed(1)}bp (전일 대비)</div>
        <div class="pct">1년 중 위치 ${pr} / 100</div>
        <div class="bar"><i style="left:calc(${pr}% - 2px)"></i></div></div>`);
  }
}
function fill(chart, series){
  const s = range ? Math.max(0, D.date.length - range) : 0;
  chart.data.labels = D.date.slice(s);
  chart.data.datasets = series.filter(([k]) => D[k]).map(([k,name],i) => ({
    label:name, data:D[k].slice(s), borderColor:COLORS[i], backgroundColor:COLORS[i],
    borderWidth:2, pointRadius:0, tension:0.15, spanGaps:true }));
  chart.update();
}
function render(){
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.id === cur.id));
  document.getElementById("desc").textContent = cur.desc;
  document.getElementById("t1").textContent = cur.c1[0];
  document.getElementById("t2").textContent = cur.c2[0];
  renderCards(); fill(ch1, cur.c1[1]); fill(ch2, cur.c2[1]);
}

const tabsEl = document.getElementById("tabs");
for (const t of TABS){
  const b = document.createElement("button"); b.textContent = t.name; b.dataset.id = t.id;
  b.onclick = () => { cur = t; history.replaceState(null, "", "#" + t.id); render(); };
  tabsEl.appendChild(b);
}
document.querySelectorAll("#ranges button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#ranges button").forEach(x => x.classList.remove("on"));
  b.classList.add("on"); range = +b.dataset.d; render();
});
cur = TABS.find(t => "#" + t.id === location.hash) || TABS[0];
render();
</script>
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__BUILT__", built))
print(f"대시보드 생성: {OUT} (최신 {payload['date'][-1]})")
