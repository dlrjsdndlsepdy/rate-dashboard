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
  .label { color:var(--muted); font-size:12px; text-decoration:none; display:block; }
  a.label:hover { color:var(--accent); }
  .sub a, .desc a { color:var(--accent); text-decoration:none; }
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
  <div class="sub">최신 데이터 <b id="asof"></b> · 페이지 생성 __BUILT__ · <a href="daily.html">🧭 오늘의 해석</a> · <a href="guide.html">📘 지표 가이드</a> · <a href="us.html">🇺🇸 미국</a> · <a href="markets.html">📈 증시</a> · <a href="weekly.html">🗓️ 주간</a> · <a href="calc.html">🧮 계산기</a></div>

  <div class="tabs" id="tabs"></div>
  <p class="desc" id="desc"></p>
  <div class="cards" id="cards"></div>

  <div class="ranges" id="ranges">
    <button data-d="22">1개월</button><button data-d="66" class="on">3개월</button>
    <button data-d="130">6개월</button><button data-d="260">1년</button><button data-d="0">전체</button>
    <label style="margin-left:auto;font-size:13px;color:var(--muted);display:flex;align-items:center;gap:4px">
      <input type="checkbox" id="evt" checked> 금통위·FOMC 표시</label>
  </div>

  <div class="panel"><h2 id="t1"></h2><div class="chartbox"><canvas id="c1"></canvas></div></div>
  <div class="panel"><h2 id="t2"></h2><div class="chartbox"><canvas id="c2"></canvas></div></div>

  <div class="foot">
    <b>출처</b> · 한국은행 ECOS 시장금리(일별, 금융투자협회 최종호가수익률 기준): 국고채 3·10·30년, 회사채 AA− 3년, CD·CP 91일, 주식시장(코스피·코스닥).<br>
    금융투자협회 채권시가평가기준수익률(평가사 평균, 민평): 여전채 = '금융채 II(금융기관채) 무보증' AA−(1·3·5년)·A+ 3년, 은행채 = '금융채 I(은행채) 무보증' AAA 1·3년, 기업금융 탭 = '회사채 I(공모) 무보증' AA−·A−·BBB+ 3년. 민평 지표의 스프레드는 같은 민평 기준 국고채 대비.<br>
    <b>차트 세로선</b> · 빨강/파랑 = 기준금리 인상/인하일, 노랑 = FOMC 결정이 한국 시장에 반영된 날.<br>
    <b>정의</b> · 장단기 = 국고 10Y−3Y · 초장기 = 국고 30Y−10Y · 회사채 스프레드 = 회사채 AA−−국고 3Y ·
    등급 스프레드 = 여전채 A+ − AA− · CP−CD = CP 91일 − CD 91일.<br>
    '1년 중 위치'는 최근 약 260영업일 중 오늘 값보다 낮았던 날의 비율(0=1년 최저, 100=1년 최고)입니다.
  </div>
</div>

<script>
const D = __DATA__;
const EV = __EVENTS__;
let showEv = true;
// 차트 세로선 (금통위 금리 변경 · FOMC)
Chart.register({ id:"evlines", afterDatasetsDraw(chart){
  if (!showEv) return;
  const labels = chart.data.labels; if (!labels.length) return;
  const {ctx, chartArea:a, scales:{x}} = chart;
  ctx.save(); ctx.setLineDash([3,3]); ctx.lineWidth = 1; ctx.font = "10px sans-serif";
  for (const e of EV){
    if (e.d < labels[0] || e.d > labels.at(-1)) continue;
    const i = labels.findIndex(l => l >= e.d); if (i < 0) continue;
    const px = x.getPixelForValue(i);
    ctx.strokeStyle = e.c; ctx.globalAlpha = 0.7;
    ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
    if (labels.length <= 140){ ctx.fillStyle = e.c; ctx.globalAlpha = 0.9; ctx.fillText(e.t, px + 3, a.top + 10); }
  }
  ctx.restore();
}});

const COLORS = ["#4dabf7","#ffa94d","#69db7c","#da77f2","#ff8787","#ffd43b","#63e6be","#adb5bd"];
const TABS = [
  { id:"common", name:"공통",
    desc:"국고채 커브와 일반 회사채 크레딧. 모든 업권의 출발점이에요.",
    cards:[["ktb3","국고채 3년","%"],["ktb10","국고채 10년","%"],["corp_aa","회사채 AA− 3년","%"],
           ["term_spread_bp","장단기 스프레드 (10Y−3Y)","bp"],["corp_spread_bp","회사채 크레딧 스프레드","bp"]],
    c1:["국고채 · 회사채 금리 (%)", [["ktb3","국고 3년"],["ktb10","국고 10년"],["corp_aa","회사채 AA− 3년"]]],
    c2:["스프레드 (bp)", [["term_spread_bp","장단기 (10Y−3Y)"],["corp_spread_bp","회사채 AA− − 국고 3년"]]] },
  { id:"curve", name:"금리 기대·커브",
    desc:"국고채 1~30년 전체 커브와 통안증권. 통안 1·2년이 기준금리보다 낮으면 시장이 인하를, 높으면 인상을 가격에 반영하고 있다는 뜻이에요.",
    cards:[["bok_rate","한국은행 기준금리","%"],["msb1","통안증권 1년","%"],["msb2","통안증권 2년","%"],
           ["msb1_policy_bp","통안 1년 − 기준금리","bp"],["ktb1","국고채 1년","%"],["ktb2","국고채 2년","%"],
           ["ktb5","국고채 5년","%"],["ktb20","국고채 20년","%"]],
    c1:["국고채 커브 (%)", [["ktb1","1년"],["ktb2","2년"],["ktb3","3년"],["ktb5","5년"],["ktb10","10년"],["ktb20","20년"],["ktb30","30년"]]],
    c2:["기준금리 vs 통안증권 (%)", [["bok_rate","기준금리"],["msb1","통안 1년"],["msb2","통안 2년"]]] },
  { id:"capital", name:"캐피탈",
    desc:"여전채 만기별(1·3·5년) 조달금리, 등급 간 격차(대형 AA급 vs 중소형 A급), 은행 대비 조달 격차, 단기 조달시장(CP) 온도.",
    cards:[["yeojeon_aa_1y","여전채 AA− 1년","%"],["yeojeon_aa","여전채 AA− 3년","%"],["yeojeon_aa_5y","여전채 AA− 5년","%"],
           ["yeojeon_a_plus","여전채 A+ 3년","%"],
           ["yeojeon_spread_bp","여전채 AA− 크레딧 스프레드","bp"],["yeojeon_grade_bp","등급 스프레드 (A+ − AA−)","bp"],
           ["yeojeon_term_bp","여전채 기간 프리미엄 (5Y − 1Y)","bp"],["yeojeon_bank_bp","여전채 − 은행채 격차","bp"],
           ["cp91","CP 91일","%"],["cp_cd_spread_bp","CP − CD 스프레드","bp"]],
    c1:["여전채 만기별 · 단기 조달금리 (%)", [["yeojeon_aa_1y","여전채 AA− 1년"],["yeojeon_aa","여전채 AA− 3년"],["yeojeon_aa_5y","여전채 AA− 5년"],["yeojeon_a_plus","여전채 A+ 3년"],["cp91","CP 91일"]]],
    c2:["캐피탈 스프레드 (bp)", [["yeojeon_spread_bp","여전채 AA− − 국고 3년"],["yeojeon_grade_bp","A+ − AA−"],["yeojeon_bank_bp","여전채 − 은행채"],["yeojeon_term_bp","5Y − 1Y"],["cp_cd_spread_bp","CP − CD"]]] },
  { id:"credit", name:"기업금융",
    desc:"캐피탈 기업금융의 실제 고객층인 중견·중소기업(A~BBB급) 조달금리. 등급 간 격차가 벌어지면 하위 등급 기업의 시장 조달이 어려워지고, 여신·사모 크레딧의 역할이 커져요.",
    cards:[["corp_aa_mp","회사채 AA− 3년 (민평)","%"],["corp_a_minus","회사채 A− 3년","%"],["corp_bbb_plus","회사채 BBB+ 3년","%"],
           ["corp_a_spread_bp","A− 크레딧 스프레드 (vs 국고)","bp"],["corp_grade_a_bp","등급 스프레드 (A− − AA−)","bp"],["corp_grade_bbb_bp","등급 스프레드 (BBB+ − AA−)","bp"]],
    c1:["등급별 회사채 3년 (%)", [["ktb3_mp","국고 3년 (민평)"],["corp_aa_mp","AA−"],["corp_a_minus","A−"],["corp_bbb_plus","BBB+"]]],
    c2:["등급 간 스프레드 (bp)", [["corp_grade_a_bp","A− − AA−"],["corp_grade_bbb_bp","BBB+ − AA−"],["corp_a_spread_bp","A− − 국고 3년"]]] },
  { id:"insurance", name:"보험",
    desc:"보험사 ALM·K-ICS의 핵심인 초장기 구간. 10-30 스프레드가 낮거나 역전이면 초장기채 수요가 강하다는 신호예요.",
    cards:[["ktb10","국고채 10년","%"],["ktb20","국고채 20년","%"],["ktb30","국고채 30년","%"],["ultra_spread_bp","초장기 스프레드 (30Y−10Y)","bp"],
           ["term_spread_bp","장단기 스프레드 (10Y−3Y)","bp"]],
    c1:["장기 · 초장기 국고채 (%)", [["ktb3","국고 3년"],["ktb5","국고 5년"],["ktb10","국고 10년"],["ktb20","국고 20년"],["ktb30","국고 30년"]]],
    c2:["커브 기울기 (bp)", [["ultra_spread_bp","30Y − 10Y"],["term_spread_bp","10Y − 3Y"]]] },
  { id:"bank", name:"은행",
    desc:"은행의 시장 조달금리(은행채 AAA), 대출 기준금리인 CD, 그리고 단기 자금시장 스트레스(CP−CD).",
    cards:[["bank_aaa_1y","은행채 AAA 1년","%"],["bank_aaa","은행채 AAA 3년","%"],["bank_spread_bp","은행채 AAA 스프레드 (vs 국고 3년)","bp"],
           ["cd91","CD 91일","%"],["cp91","CP 91일","%"],["cp_cd_spread_bp","CP − CD 스프레드","bp"]],
    c1:["은행 조달 · 단기 금리 (%)", [["bank_aaa_1y","은행채 AAA 1년"],["bank_aaa","은행채 AAA 3년"],["cd91","CD 91일"],["cp91","CP 91일"],["ktb3_mp","국고 3년 (민평)"]]],
    c2:["은행 스프레드 (bp)", [["bank_spread_bp","은행채 AAA − 국고 3년"],["cp_cd_spread_bp","CP − CD"]]] },
  { id:"risk", name:"위험자산",
    desc:"주식은 신용위험의 선행지표예요. 기업이 어려워지면 보통 주가가 먼저 빠지고 크레딧 스프레드가 뒤따라 벌어져요. 둘이 같은 방향이면 신호가 강하고, 엇갈리면 경고 신호예요.",
    cards:[["kospi","코스피","idx"],["kosdaq","코스닥","idx"],["corp_spread_bp","회사채 크레딧 스프레드","bp"],
           ["yeojeon_spread_bp","여전채 AA− 크레딧 스프레드","bp"],["corp_a_spread_bp","A− 크레딧 스프레드","bp"]],
    c1:["코스피 vs 회사채 크레딧 스프레드", [["kospi","코스피 (왼쪽)"],["corp_spread_bp","회사채 AA− 스프레드 (bp, 오른쪽)","right"]]],
    c2:["코스닥 vs A− 크레딧 스프레드", [["kosdaq","코스닥 (왼쪽)"],["corp_a_spread_bp","A− 스프레드 (bp, 오른쪽)","right"]]] },
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
    // idx(주가지수): 변화를 %로 / %: 금리, 변화를 bp로 / bp: 스프레드
    const diffBp = unit === "%" ? (val - p[0]) * 100 : unit === "idx" ? (val / p[0] - 1) * 100 : (val - p[0]);
    const du = unit === "idx" ? "%" : "bp";
    const cls = diffBp > 0.005 ? "up" : diffBp < -0.005 ? "down" : "flat";
    const arrow = cls === "up" ? "▲" : cls === "down" ? "▼" : "–";
    const shown = unit === "%" ? val.toFixed(3) + "%" : unit === "idx"
      ? val.toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:2}) : val.toFixed(1) + "bp";
    const pr = pctRank(D[k]);
    el.insertAdjacentHTML("beforeend", `
      <div class="card"><a class="label" href="guide.html#${k}" title="이 지표 설명 보기">${name} ⓘ</a>
        <div class="val">${shown}</div>
        <div class="chg ${cls}">${arrow} ${Math.abs(diffBp).toFixed(unit === "idx" ? 2 : 1)}${du} (전일 대비)</div>
        <div class="pct">1년 중 위치 ${pr} / 100</div>
        <div class="bar"><i style="left:calc(${pr}% - 2px)"></i></div></div>`);
  }
}
function fill(chart, series){
  const s = range ? Math.max(0, D.date.length - range) : 0;
  chart.data.labels = D.date.slice(s);
  chart.data.datasets = series.filter(([k]) => D[k]).map(([k,name,side],i) => ({
    label:name, data:D[k].slice(s), borderColor:COLORS[i], backgroundColor:COLORS[i],
    borderWidth:2, pointRadius:0, tension:0.15, spanGaps:true, yAxisID: side === "right" ? "y1" : "y" }));
  // 오른쪽 축은 그 축을 쓰는 지표가 있을 때만 표시
  chart.options.scales.y1 = { position:"right", display: series.some(x => x[2] === "right"), grid:{ drawOnChartArea:false } };
  chart.update();
}
function render(){
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.id === cur.id));
  document.getElementById("desc").innerHTML = cur.desc + ` <a href="guide.html#${cur.id}">지표 설명 보기 →</a>`;
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
document.getElementById("evt").onchange = e => { showEv = e.target.checked; render(); };
cur = TABS.find(t => "#" + t.id === location.hash) || TABS[0];
render();
</script>
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    try:
        import events
        ev = events.chart_lines(df.set_index("date"))
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 이벤트 세로선 생략: {e}")
        ev = []
    f.write(HTML.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
            .replace("__EVENTS__", json.dumps(ev, ensure_ascii=False)).replace("__BUILT__", built))
print(f"대시보드 생성: {OUT} (최신 {payload['date'][-1]})")

# 지표 가이드 페이지
import guide_page  # noqa: E402
with open(os.path.join(ROOT, "docs", "guide.html"), "w", encoding="utf-8") as f:
    f.write(guide_page.render(built))
print("지표 가이드 생성: docs/guide.html")

# 오늘의 해석 페이지 (규칙 기반)
import interpret  # noqa: E402
import institutions  # noqa: E402
with open(os.path.join(ROOT, "docs", "daily.html"), "w", encoding="utf-8") as f:
    f.write(interpret.render(df.set_index("date"), built))
print("오늘의 해석 생성: docs/daily.html")
institutions.write_logic(os.path.join(ROOT, "docs"), built)
print("해석 로직 생성: docs/logic.html")

# 주간 요약 · 캐리 계산기
for name, mod in [("주간 요약", "weekly"), ("캐리 계산기", "calc")]:
    try:
        __import__(mod).write(os.path.join(ROOT, "docs"), df.set_index("date"), built)
        print(f"{name} 생성: docs/{mod}.html")
    except Exception as e:  # noqa: BLE001
        print(f"[경고] {name} 생성 실패: {e}")

# 앱(PWA) 설치 정보
import pwa  # noqa: E402
pwa.finalize(os.path.join(ROOT, "docs"))
