"""
미국 대시보드(docs/us.html) + 미국 오늘의 해석(docs/us-daily.html) 생성.

입력: data/us.csv (FRED), data/rates.csv (한국), data/kr_extra.csv (기준금리·환율)
한미 비교 날짜 맞추기: 한국 날짜 t에는 '미국 날짜 ≤ t-1일인 값 중 가장 최근 값'을 씀
(미국 장은 한국 시간 새벽에 끝나고, FRED는 보통 1~2영업일 늦게 공표하므로 실제 쓰인 미국 날짜를 함께 표시)
"""
import json
import math
import os
import datetime as dt

import pandas as pd

import minichart

ROOT = os.path.dirname(__file__)
D = lambda *p: os.path.join(ROOT, *p)  # noqa: E731

NOISE = {"default": 1.0, "ig_bp": 2.0, "hy_bp": 2.0, "hy_ig_bp": 2.0, "usdkrw": 2.0, "sp500": 0.3, "vix": 1.0}
SIGMA_K, HI_PCT, LO_PCT, WINDOW, TREND_N, HISTORY_N = 2.0, 90, 10, 260, 5, 20

# 표시 이름, 단위(% → 변화는 bp로 / bp / 원)
NAMES = {
    "ust3m": ("미 국채 3개월", "%"), "ust2": ("미 국채 2년", "%"), "ust10": ("미 국채 10년", "%"),
    "ust30": ("미 국채 30년", "%"), "fed_upper": ("연준 기준금리 상단", "%"), "fed_lower": ("연준 기준금리 하단", "%"),
    "effr": ("실효 연방기금금리", "%"), "sofr": ("SOFR", "%"), "tips10": ("10년 실질금리(TIPS)", "%"),
    "bei10": ("10년 기대인플레이션(BEI)", "%"), "s2s10_bp": ("2s10s (10Y−2Y)", "bp"),
    "s3m10_bp": ("10Y−3M", "bp"), "s10s30_bp": ("30Y−10Y", "bp"), "policy_gap_bp": ("정책 기대 갭 (2Y−기준금리)", "bp"),
    "ig_bp": ("투자등급(IG) 스프레드", "bp"), "hy_bp": ("하이일드(HY) 스프레드", "bp"), "hy_ig_bp": ("HY − IG", "bp"),
    # 한미 비교(K 프레임)
    "ktb10": ("한국 국고 10년", "%"), "ust10_k": ("미 국채 10년", "%"), "kr_us10_bp": ("한미 10년 금리차 (한−미)", "bp"),
    "bok_rate": ("한국은행 기준금리", "%"), "fed_upper_k": ("연준 기준금리 상단", "%"),
    "rate_gap_bp": ("한미 기준금리차 (한−미 상단)", "bp"), "usdkrw": ("원/달러 환율", "원"),
    "hedge_bp": ("환헤지 비용 근사 (미 3M − CD 91일)", "bp"),
    # 위험자산 (idx: 변화를 %로, pt: 변화를 포인트로)
    "sp500": ("S&P 500", "idx"), "vix": ("VIX", "pt"),
}


# ---------------------------------------------------------------------------
# 데이터 준비
# ---------------------------------------------------------------------------
def load():
    us = pd.read_csv(D("data", "us.csv"), parse_dates=["date"]).set_index("date").sort_index()
    kr = pd.read_csv(D("data", "rates.csv"), parse_dates=["date"]).set_index("date").sort_index()
    ex_path = D("data", "kr_extra.csv")
    ex = pd.read_csv(ex_path, parse_dates=["date"]).set_index("date").sort_index() if os.path.exists(ex_path) else None

    # 한국 날짜 기준 프레임: 미국 값은 (미국 날짜 + 1일) ≤ 한국 날짜 인 가장 최근 값
    k = kr[["ktb10", "ktb3"] + (["cd91"] if "cd91" in kr.columns else [])].copy()
    u = us[["ust10", "ust3m", "fed_upper"]].copy()
    u["us_src"] = u.index                      # 실제로 쓰인 미국 날짜(표시용)
    u.index = u.index + pd.Timedelta(days=1)
    k = pd.merge_asof(k.sort_index(), u.sort_index(), left_index=True, right_index=True, direction="backward")
    k = k.rename(columns={"ust10": "ust10_k", "fed_upper": "fed_upper_k", "ust3m": "ust3m_k"})
    if ex is not None:
        k = pd.merge_asof(k, ex.sort_index(), left_index=True, right_index=True, direction="backward")
    k["kr_us10_bp"] = ((k["ktb10"] - k["ust10_k"]) * 100).round(1)
    if "bok_rate" in k.columns:
        k["rate_gap_bp"] = ((k["bok_rate"] - k["fed_upper_k"]) * 100).round(1)
    if "cd91" in k.columns:
        k["hedge_bp"] = ((k["ust3m_k"] - k["cd91"]) * 100).round(1)
    k = k.drop(columns=[c for c in ["ktb3", "cd91", "ust3m_k"] if c in k.columns])
    return us, k


# ---------------------------------------------------------------------------
# 대시보드 (us.html)
# ---------------------------------------------------------------------------
TABS_JS = r"""
const TABS = [
  { id:"curve", name:"커브", src:"U",
    desc:"미 국채 수익률 곡선. 미국은 2년과 10년의 차이(2s10s)가 대표 지표이고, 역전(마이너스)은 경기침체 신호로 유명해요.",
    cards:[["ust2","미 국채 2년","%"],["ust10","미 국채 10년","%"],["ust30","미 국채 30년","%"],["s2s10_bp","2s10s (10Y−2Y)","bp"],["s3m10_bp","10Y−3M","bp"]],
    charts:[["미 국채 금리 (%)",[["ust3m","3개월"],["ust2","2년"],["ust10","10년"],["ust30","30년"]]],
            ["커브 기울기 (bp)",[["s2s10_bp","10Y−2Y"],["s3m10_bp","10Y−3M"],["s10s30_bp","30Y−10Y"]]]] },
  { id:"policy", name:"정책·단기", src:"U",
    desc:"연준 기준금리와 단기 자금시장. 2년 금리와 기준금리의 차이(정책 기대 갭)로 시장이 예상하는 금리 경로를 읽어요.",
    cards:[["fed_upper","연준 기준금리 상단","%"],["effr","실효 연방기금금리","%"],["sofr","SOFR","%"],["ust2","미 국채 2년","%"],["policy_gap_bp","정책 기대 갭 (2Y−기준금리)","bp"]],
    charts:[["정책금리와 단기금리 (%)",[["fed_upper","기준금리 상단"],["fed_lower","기준금리 하단"],["effr","실효 FF"],["sofr","SOFR"],["ust2","국채 2년"]]],
            ["정책 기대 갭 (bp)",[["policy_gap_bp","2Y − 기준금리 중간값"]]]] },
  { id:"credit", name:"크레딧", src:"U",
    desc:"미국 회사채 스프레드(ICE BofA OAS). 하이일드 스프레드는 글로벌 위험 선호를 가장 먼저 보여주는 지표예요.",
    cards:[["ig_bp","투자등급(IG) 스프레드","bp"],["hy_bp","하이일드(HY) 스프레드","bp"],["hy_ig_bp","HY − IG","bp"],["ust10","미 국채 10년","%"]],
    charts:[["회사채 스프레드 (bp)",[["ig_bp","투자등급(IG)"],["hy_bp","하이일드(HY)"]]],
            ["등급 간 격차 (bp)",[["hy_ig_bp","HY − IG"]]]] },
  { id:"inflation", name:"물가·실질", src:"U",
    desc:"10년 금리 = 실질금리(TIPS) + 기대인플레이션(BEI). 금리가 왜 움직였는지 둘로 나눠 볼 수 있어요.",
    cards:[["ust10","미 국채 10년","%"],["tips10","10년 실질금리(TIPS)","%"],["bei10","10년 기대인플레이션(BEI)","%"]],
    charts:[["10년 금리 분해 (%)",[["ust10","명목 10년"],["tips10","실질금리"],["bei10","기대인플레이션"]]]] },
  { id:"risk", name:"위험자산", src:"U",
    desc:"S&P 500과 VIX(공포지수)를 하이일드 스프레드와 함께 봐요. 주가 하락·VIX 급등·HY 확대가 겹치면 글로벌 Risk-off가 확인되고, 주가는 오르는데 HY가 벌어지면 크레딧이 먼저 보내는 경고예요.",
    cards:[["sp500","S&P 500","idx"],["vix","VIX","pt"],["hy_bp","하이일드(HY) 스프레드","bp"],["ig_bp","투자등급(IG) 스프레드","bp"]],
    charts:[["S&P 500 vs 하이일드 스프레드",[["sp500","S&P 500 (왼쪽)"],["hy_bp","HY 스프레드 (bp, 오른쪽)","right"]]],
            ["VIX vs 하이일드 스프레드",[["vix","VIX (왼쪽)"],["hy_bp","HY 스프레드 (bp, 오른쪽)","right"]]]] },
  { id:"korea", name:"한미 비교", src:"K",
    desc:"한국 날짜 기준. 미국 값은 그 시점에 공표돼 있던 가장 최근 값이에요(FRED는 보통 1~2영업일 늦게 공표). 금리차는 외국인 채권 수급·환율과, 단기 금리차는 보험사 해외투자의 환헤지 비용과 연결돼요.",
    cards:[["ktb10","한국 국고 10년","%"],["ust10_k","미 국채 10년","%"],["kr_us10_bp","한미 10년 금리차 (한−미)","bp"],
           ["bok_rate","한국은행 기준금리","%"],["rate_gap_bp","한미 기준금리차 (한−미 상단)","bp"],["hedge_bp","환헤지 비용 근사 (미 3M − CD 91일)","bp"],["usdkrw","원/달러 환율","원"]],
    charts:[["한미 10년 금리 (%)",[["ktb10","한국 10년"],["ust10_k","미국 10년"]]],
            ["한미 금리차 (bp)",[["kr_us10_bp","10년 금리차"],["rate_gap_bp","기준금리차"],["hedge_bp","환헤지 비용 근사"]]],
            ["원/달러 환율 (원)",[["usdkrw","원/달러"]]]] },
];
"""

PAGE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US Rates & Credit Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3; --up:#ff6b6b; --down:#4dabf7; --accent:#4dabf7; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; background:var(--bg); color:var(--fg); }
  a { color:var(--accent); text-decoration:none; }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:18px; }
  .tabs { display:flex; gap:4px; border-bottom:1px solid var(--line); margin-bottom:16px; flex-wrap:wrap; }
  .tabs button { background:none; border:none; color:var(--muted); font-size:15px; padding:10px 16px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
  .tabs button.on { color:var(--fg); border-bottom-color:var(--accent); font-weight:700; }
  .desc { color:var(--muted); font-size:13px; margin:0 0 14px; line-height:1.6; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .label { color:var(--muted); font-size:12px; display:block; } a.label:hover { color:var(--accent); }
  .val { font-size:26px; font-weight:700; margin:4px 0 2px; font-variant-numeric:tabular-nums; }
  .chg { font-size:13px; font-variant-numeric:tabular-nums; }
  .up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--muted); }
  .pct { color:var(--muted); font-size:12px; margin-top:6px; }
  .bar { height:4px; background:var(--line); border-radius:2px; margin-top:4px; position:relative; }
  .bar i { position:absolute; top:-3px; width:4px; height:10px; border-radius:2px; background:var(--fg); }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
  .panel h2 { font-size:15px; margin:0 0 10px; }
  .ranges { display:flex; gap:6px; margin-bottom:14px; }
  .ranges button { background:var(--card); color:var(--fg); border:1px solid var(--line); border-radius:8px; padding:6px 12px; cursor:pointer; font-size:13px; }
  .ranges button.on { background:var(--accent); border-color:var(--accent); color:#0b1015; font-weight:700; }
  .chartbox { position:relative; height:300px; }
  .foot { color:var(--muted); font-size:12px; margin-top:20px; line-height:1.7; }
</style></head>
<body><div class="wrap">
  <h1>🇺🇸 미국 금리 · 크레딧 대시보드</h1>
  <div class="sub">미국 최신 <b id="asofU"></b> · 한미 비교 최신 <b id="asofK"></b> · 페이지 생성 __BUILT__<br>
    <a href="index.html">🇰🇷 한국 대시보드</a> · <a href="markets.html">📈 증시</a> · <a href="us-daily.html">🧭 미국 오늘의 해석</a> · <a href="guide.html#us">📘 지표 가이드</a></div>
  <div class="tabs" id="tabs"></div>
  <p class="desc" id="desc"></p>
  <div class="cards" id="cards"></div>
  <div class="ranges" id="ranges">
    <button data-d="22">1개월</button><button data-d="66" class="on">3개월</button>
    <button data-d="130">6개월</button><button data-d="260">1년</button><button data-d="0">전체</button>
  </div>
  <div id="charts"></div>
  <div class="foot">
    <b>출처</b> · FRED(세인트루이스 연준): 미 국채 DGS3MO·DGS2·DGS10·DGS30, 연준 기준금리 DFEDTARU·DFEDTARL, 실효 FF DFF, SOFR, 10년 TIPS DFII10,
    ICE BofA 미국 회사채 OAS(투자등급 BAMLC0A0CM, 하이일드 BAMLH0A0HYM2), S&P 500(SP500), VIX(VIXCLS). 한국: 한국은행 ECOS(국고 10년, CD 91일, 기준금리, 원/달러 매매기준율).<br>
    <b>정의</b> · 기대인플레이션(BEI) = 명목 10년 − TIPS 10년 · 정책 기대 갭 = 국채 2년 − 연준 기준금리 중간값 ·
    환헤지 비용 근사 = 미 국채 3개월 − 한국 CD 91일 (실제 스왑포인트와는 차이가 있어요).<br>
    '1년 중 위치'는 최근 약 260영업일 중 오늘 값보다 낮았던 날의 비율(0=1년 최저, 100=1년 최고)입니다.
  </div>
</div>
<script>
const DS = __DATA__;
__TABS__
const COLORS = ["#4dabf7","#ffa94d","#69db7c","#da77f2","#ff8787","#ffd43b"];
function lastTwo(a){ const v=a.map((x,i)=>[x,i]).filter(p=>p[0]!==null); return [v.at(-1), v.at(-2)]; }
function pctRank(a,n=260){ const v=a.filter(x=>x!==null).slice(-n); const t=v.at(-1); return Math.round(100*v.filter(x=>x<t).length/(v.length-1||1)); }
document.getElementById("asofU").textContent = DS.U.date.at(-1);
document.getElementById("asofK").textContent = DS.K.date.at(-1);
Chart.defaults.color="#8b95a3"; Chart.defaults.borderColor="#2a323d";
let cur=TABS[0], range=66, charts=[];
function render(){
  const D = DS[cur.src];
  document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on", b.dataset.id===cur.id));
  document.getElementById("desc").innerHTML = cur.desc + ` <a href="guide.html#us-${cur.id}">지표 설명 보기 →</a>`;
  const el=document.getElementById("cards"); el.innerHTML="";
  for (const [k,name,unit] of cur.cards){
    if(!D[k] || D[k].every(x=>x===null)) continue;
    const [c,p]=lastTwo(D[k]); const val=c[0];
    const diff = unit==="%" ? (val-p[0])*100 : unit==="idx" ? (val/p[0]-1)*100 : (val-p[0]);
    const du = unit==="원" ? "원" : unit==="idx" ? "%" : unit==="pt" ? "pt" : "bp";
    const cls = diff>0.005?"up":diff<-0.005?"down":"flat"; const ar = cls==="up"?"▲":cls==="down"?"▼":"–";
    const shown = unit==="%" ? val.toFixed(3)+"%" : unit==="원" ? val.toFixed(1)+"원" : unit==="idx"
      ? val.toLocaleString("en-US",{minimumFractionDigits:2, maximumFractionDigits:2}) : unit==="pt" ? val.toFixed(2) : val.toFixed(1)+"bp";
    const pr=pctRank(D[k]);
    el.insertAdjacentHTML("beforeend", `<div class="card"><a class="label" href="guide.html#${k.replace(/_k$/,"")}">${name} ⓘ</a>
      <div class="val">${shown}</div><div class="chg ${cls}">${ar} ${Math.abs(diff).toFixed(unit==="idx"||unit==="pt"?2:1)}${du} (전일 대비)</div>
      <div class="pct">1년 중 위치 ${pr} / 100</div><div class="bar"><i style="left:calc(${pr}% - 2px)"></i></div></div>`);
  }
  charts.forEach(c=>c.destroy()); charts=[];
  const box=document.getElementById("charts"); box.innerHTML="";
  const s = range ? Math.max(0, D.date.length-range) : 0;
  cur.charts.forEach(([title, series], i)=>{
    box.insertAdjacentHTML("beforeend", `<div class="panel"><h2>${title}</h2><div class="chartbox"><canvas id="cv${i}"></canvas></div></div>`);
    charts.push(new Chart(document.getElementById("cv"+i), { type:"line",
      data:{ labels:D.date.slice(s), datasets: series.filter(([k])=>D[k]).map(([k,n,side],j)=>({label:n, data:D[k].slice(s),
        borderColor:COLORS[j], backgroundColor:COLORS[j], borderWidth:2, pointRadius:0, tension:0.15, spanGaps:true,
        yAxisID: side==="right" ? "y1" : "y"})) },
      options:{ responsive:true, maintainAspectRatio:false, interaction:{mode:"index", intersect:false},
        plugins:{legend:{labels:{boxWidth:12}}}, scales:{x:{ticks:{maxTicksLimit:8}},
        y1:{position:"right", display: series.some(x=>x[2]==="right"), grid:{drawOnChartArea:false}}} } }));
  });
}
const tabsEl=document.getElementById("tabs");
for(const t of TABS){ const b=document.createElement("button"); b.textContent=t.name; b.dataset.id=t.id;
  b.onclick=()=>{ cur=t; history.replaceState(null,"","#"+t.id); render(); }; tabsEl.appendChild(b); }
document.querySelectorAll("#ranges button").forEach(b=>b.onclick=()=>{ document.querySelectorAll("#ranges button").forEach(x=>x.classList.remove("on")); b.classList.add("on"); range=+b.dataset.d; render(); });
cur = TABS.find(t=>"#"+t.id===location.hash) || TABS[0];
render();
</script></body></html>
"""


def payload(df: pd.DataFrame) -> dict:
    p = {"date": df.index.strftime("%Y-%m-%d").tolist()}
    for c in df.columns:
        p[c] = [None if pd.isna(v) else round(float(v), 4) for v in df[c]]
    return p


# ---------------------------------------------------------------------------
# 해석 (us-daily.html)
# ---------------------------------------------------------------------------
def _bp(x, unit="bp"):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    s = "+" if x > 0 else ("−" if x < 0 else "±")
    return f"{s}{abs(x):.1f}{unit}"


class Day:
    def __init__(self, df, i):
        self.df, self.i, self.date = df, i, df.index[i]

    def has(self, c):
        return c in self.df.columns and not pd.isna(self.df[c].iloc[self.i]) and not pd.isna(self.df[c].iloc[self.i - 1])

    def sc(self, c):
        return 100.0 if NAMES.get(c, ("", "%"))[1] == "%" else 1.0

    def lvl(self, c):
        return float(self.df[c].iloc[self.i])

    def _chg(self, c, a, b):
        return (b / a - 1) * 100 if NAMES.get(c, ("", "%"))[1] == "idx" else (b - a) * self.sc(c)

    def d(self, c):
        return self._chg(c, self.df[c].iloc[self.i - 1], self.df[c].iloc[self.i]) if self.has(c) else float("nan")

    def d5(self, c):
        j = self.i - TREND_N
        if c not in self.df.columns or j < 0 or pd.isna(self.df[c].iloc[j]) or pd.isna(self.df[c].iloc[self.i]):
            return float("nan")
        return self._chg(c, self.df[c].iloc[j], self.df[c].iloc[self.i])

    def sigma(self, c):
        w = self.df[c].iloc[max(0, self.i - WINDOW): self.i + 1]
        s = (w.pct_change() * 100 if NAMES.get(c, ("", "%"))[1] == "idx" else w.diff() * self.sc(c)).dropna()
        s = s[s != 0] if c in ("fed_upper", "fed_lower", "bok_rate", "fed_upper_k") else s
        return float(s.std()) if len(s) > 20 else float("nan")

    def pct(self, c):
        s = self.df[c].iloc[max(0, self.i - WINDOW + 1): self.i + 1].dropna()
        return float("nan") if len(s) < 20 else round(100 * (s < s.iloc[-1]).sum() / (len(s) - 1))


def _dir(x, c="default"):
    n = NOISE.get(c, NOISE["default"])
    if x is None or math.isnan(x) or abs(x) < n:
        return 0
    return 1 if x > 0 else -1


def _lvl(c, v):
    u = NAMES.get(c, ("", "%"))[1]
    if u == "idx":
        return f"{v:,.2f}"
    if u == "pt":
        return f"{v:.2f}"
    return f"{v:.3f}%" if u == "%" else (f"{v:.1f}원" if u == "원" else f"{v:.1f}bp")


def curve_regime(d2, d10):
    if math.isnan(d2) or math.isnan(d10):
        return None, None
    a, b = _dir(d2), _dir(d10)
    if a == 0 and b == 0:
        return "보합", "2년·10년 모두 1bp 미만 변동."
    if a <= 0 and b <= 0:
        return ("불 스티프닝 (U1)", "단기(2년)가 더 크게 하락 → 연준 인하 기대 확대.") if d2 < d10 else \
               ("불 플래트닝 (U2)", "장기(10년)가 더 크게 하락 → 경기 둔화 우려·안전자산 수요.")
    if a >= 0 and b >= 0:
        return ("베어 플래트닝 (U3)", "단기(2년)가 더 크게 상승 → 연준 긴축(인하 지연) 기대.") if d2 > d10 else \
               ("베어 스티프닝 (U4)", "장기(10년)가 더 크게 상승 → 물가·재정 적자 우려, 기간 프리미엄 상승.")
    return ("트위스트 (U5)", "2년↑·10년↓ → 단기 긴축 기대와 장기 둔화 전망이 엇갈림.") if d2 > 0 else \
           ("트위스트 (U5)", "2년↓·10년↑ → 인하 기대와 장기 물가·재정 우려가 엇갈림.")


def interpret_us(t: Day) -> dict:
    o = {"date": t.date.strftime("%Y-%m-%d"), "facts": [], "signals": [], "flags": [], "trends": []}
    d2, d10 = t.d("ust2"), t.d("ust10")
    o["regime"], o["regime_why"] = curve_regime(d2, d10)
    o["regime5"], _ = curve_regime(t.d5("ust2"), t.d5("ust10"))
    if t.has("ust10"):
        o["facts"].append(f"미 국채 2년 {t.lvl('ust2'):.2f}% ({_bp(d2)}), 10년 {t.lvl('ust10'):.2f}% ({_bp(d10)}), "
                          f"2s10s {t.lvl('s2s10_bp'):.1f}bp ({_bp(t.d('s2s10_bp'))})")

    # U6 금리 분해
    if t.has("tips10") and t.has("bei10") and _dir(d10):
        dr, de = t.d("tips10"), t.d("bei10")
        if abs(dr) >= abs(de):
            why = "실질금리 주도 → 성장 기대 변화·연준 긴축 강도에 대한 시장 판단이 움직인 날" if d10 > 0 else \
                  "실질금리 주도 하락 → 성장 둔화 우려 또는 완화 기대"
        else:
            why = "기대인플레이션 주도 → 물가(유가 등) 우려가 금리를 끌어올린 날" if d10 > 0 else \
                  "기대인플레이션 주도 하락 → 물가 우려 완화"
        o["signals"].append(("U6", f"10년 {_bp(d10)} = 실질금리 {_bp(dr)} + 기대인플레 {_bp(de)} → {why}", ["tips10", "bei10"]))

    # U7 정책 기대 갭
    if t.has("policy_gap_bp"):
        g, dg = t.lvl("policy_gap_bp"), t.d("policy_gap_bp")
        if _dir(dg) < 0:
            o["signals"].append(("U7", f"정책 기대 갭 {_bp(dg)} → 시장의 연준 인하 기대 강화", ["policy_gap_bp"]))
        elif _dir(dg) > 0:
            o["signals"].append(("U7", f"정책 기대 갭 {_bp(dg)} → 인하 기대 후퇴(또는 인상 기대)", ["policy_gap_bp"]))
        if g <= -25:
            o["signals"].append(("U7", f"2년 금리가 기준금리 중간값보다 {abs(g):.0f}bp 낮음 → 앞으로 2년간 대략 {abs(g) / 25:.1f}회(25bp 기준) 인하를 반영하는 수준", ["policy_gap_bp"]))
        elif g >= 25:
            o["signals"].append(("U7", f"2년 금리가 기준금리 중간값보다 {g:.0f}bp 높음 → 추가 인상 또는 인하 지연을 반영하는 수준", ["policy_gap_bp"]))

    # U8 글로벌 Risk-off / U9 차별화
    if t.has("hy_bp"):
        dh = t.d("hy_bp")
        if _dir(d10) < 0 and _dir(dh, "hy_bp") > 0:
            o["signals"].append(("U8", f"미 국채 금리↓ + HY 스프레드 {_bp(dh)} → 글로벌 Risk-off(안전자산 선호). 국내 크레딧·외국인 수급에도 부담 요인", ["ust10", "hy_bp"]))
        elif _dir(d10) > 0 and _dir(dh, "hy_bp") < 0:
            o["signals"].append(("U8", f"미 국채 금리↑ + HY 스프레드 {_bp(dh)} → 위험 선호(Risk-on), 경기 낙관", ["ust10", "hy_bp"]))
        elif _dir(dh, "hy_bp") > 0:
            o["signals"].append(("U8", f"HY 스프레드 {_bp(dh)} 확대 → 미국 하위 등급 신용 위험 회피", ["hy_bp"]))
    if t.has("hy_ig_bp") and _dir(t.d("hy_ig_bp"), "hy_ig_bp") > 0:
        o["signals"].append(("U9", f"HY − IG {_bp(t.d('hy_ig_bp'))} → 미국 크레딧 시장 내 등급 차별화 심화", ["hy_ig_bp"]))

    # U10 역전
    for c in ["s2s10_bp", "s3m10_bp"]:
        if not t.has(c):
            continue
        now, prev = t.lvl(c), float(t.df[c].iloc[t.i - 1])
        if now < 0 <= prev:
            o["signals"].append(("U10", f"{NAMES[c][0]} {now:.1f}bp로 새로 역전 → 경기침체 경계 신호", [c]))
        elif now >= 0 > prev:
            o["signals"].append(("U10", f"{NAMES[c][0]} 역전 해소({now:.1f}bp). 과거엔 역전 해소 국면이 경기 둔화 본격화와 겹친 사례가 많아 주의 깊게 볼 구간", [c]))
        elif now < 0:
            o["signals"].append(("U10", f"{NAMES[c][0]} {now:.1f}bp, 역전 지속", [c]))

    _risk_rules(t, o)
    _flags(t, o, [c for c in NAMES if not c.endswith("_k") and c in t.df.columns])
    for c in ["ust2", "ust10", "hy_bp", "sp500"]:
        if t.has(c):
            a, b = _dir(t.d(c), c), _dir(t.d5(c), c)
            if a and b:
                u = "%" if NAMES[c][1] == "idx" else "bp"
                o["trends"].append(f"{NAMES[c][0]} 5일 {_bp(t.d5(c), u)} → " + ("추세 지속" if a == b else "오늘은 되돌림"))
    return o


def _risk_rules(t: Day, o: dict):
    """U13/U14: 주식·VIX × 하이일드 스프레드 교차."""
    if t.has("vix") and t.has("hy_bp"):
        v, dv, dh = t.lvl("vix"), t.d("vix"), t.d("hy_bp")
        if _dir(dv, "vix") > 0 and _dir(dh, "hy_bp") > 0:
            o["signals"].append(("U13", f"VIX {_bp(dv, 'pt')} 상승 + HY 스프레드 {_bp(dh)} → 주식 변동성과 신용위험이 같이 커짐. 글로벌 Risk-off 확인", ["vix", "hy_bp"]))
        if v >= 30:
            o["signals"].append(("U13", f"VIX {v:.1f} → 30 이상 '공포' 구간. 위험자산 전반의 변동성 확대 국면", ["vix"]))
        elif v >= 20 and _dir(dv, "vix") > 0:
            o["signals"].append(("U13", f"VIX {v:.1f} → 20~30 '경계' 구간으로 상승", ["vix"]))
    if t.has("sp500") and t.has("hy_bp"):
        k5, h5 = t.d5("sp500"), t.d5("hy_bp")
        cc = ["sp500", "hy_bp"]
        if k5 >= 1 and h5 >= 10:
            o["signals"].append(("U14", f"5일간 S&P 500 {_bp(k5, '%')}인데 HY 스프레드 {_bp(h5)} → 주가는 오르는데 크레딧은 경계하는 괴리. 크레딧이 먼저 경고하는 경우가 많아 주의", cc))
        elif k5 <= -3 and abs(h5) < 10:
            o["signals"].append(("U14", f"5일간 S&P 500 {_bp(k5, '%')} 하락에도 HY 스프레드 {_bp(h5)} → 주식 단독 조정, 아직 신용시장 전이는 제한적", cc))


def interpret_kr(t: Day, k: pd.DataFrame) -> dict:
    """한미 연결(U11, U12) + 업권 시사점. 한국 날짜 기준."""
    o = {"date": t.date.strftime("%Y-%m-%d"), "facts": [], "signals": [], "flags": [], "sector": {}}
    if t.has("kr_us10_bp"):
        src = k["us_src"].iloc[t.i]
        src_s = f"{src:%m/%d} 기준" if not pd.isna(src) else "최근 공표값"
        o["facts"].append(f"한국 10년 {t.lvl('ktb10'):.3f}% ({_bp(t.d('ktb10'))}), 미국 10년({src_s}) {t.lvl('ust10_k'):.2f}% "
                          f"({_bp(t.d('ust10_k'))}), 금리차 {t.lvl('kr_us10_bp'):.1f}bp ({_bp(t.d('kr_us10_bp'))})")
        dg = _dir(t.d("kr_us10_bp"))
        if dg < 0:
            o["signals"].append(("U11", f"한미 10년 금리차 {_bp(t.d('kr_us10_bp'))} → 한국 금리가 상대적으로 더 낮아짐. 외국인 채권 자금 유출 압력·원화 약세 요인", ["kr_us10_bp"]))
        elif dg > 0:
            o["signals"].append(("U11", f"한미 10년 금리차 {_bp(t.d('kr_us10_bp'))} → 금리차 축소(한국 상대 금리 상승). 원화에는 지지 요인", ["kr_us10_bp"]))
    # U12 동조화
    if t.has("ust10_k") and t.has("ktb10"):
        su = t.sigma("ust10_k")
        du, dk = t.d("ust10_k"), t.d("ktb10")
        win = k.iloc[max(1, t.i - 119): t.i + 1]
        x, y = win["ust10_k"].diff() * 100, win["ktb10"].diff() * 100
        m = x.notna() & y.notna() & (x != 0)
        beta = float((x[m] * y[m]).sum() / (x[m] ** 2).sum()) if m.sum() > 30 else float("nan")
        if not math.isnan(su) and abs(du) > SIGMA_K * su:
            o["signals"].append(("U12", f"미 10년이 전날 {_bp(du)} 크게 움직임(2σ 초과) → 오늘 한국 10년 {_bp(dk)}"
                                        + (f", 최근 120일 동조화 계수 β≈{beta:.2f}" if not math.isnan(beta) else ""),
                                 ["ktb10", "ust10_k"]))
        elif not math.isnan(beta):
            o["facts"].append(f"한국 10년의 미 10년 동조화 계수(최근 120일, 미국 1bp 움직일 때 한국 평균 반응) β≈{beta:.2f}")
    _flags(t, o, ["kr_us10_bp", "rate_gap_bp", "usdkrw", "hedge_bp"])

    sec = o["sector"]
    if t.has("hedge_bp"):
        h = t.lvl("hedge_bp")
        sec["보험"] = (f"환헤지 비용 근사 {h:.0f}bp ({_bp(t.d('hedge_bp'))}). " +
                      ("미국채에 환헤지 투자 시 수익률이 이만큼 깎이는 구조 → 헤지 후 매력도 점검 필요." if h > 0 else
                       "헤지 시 오히려 프리미엄이 생기는 구조 → 헤지 해외채 매력 상승."))
    if t.has("usdkrw"):
        du = t.d("usdkrw")
        sec["공통"] = f"원/달러 {t.lvl('usdkrw'):.1f}원 ({_bp(du, '원')})" + \
                     (" → 원화 약세: 외화부채·달러 조달 비용 부담 확대." if _dir(du, "usdkrw") > 0 else
                      (" → 원화 강세." if _dir(du, "usdkrw") < 0 else " → 보합."))
    if t.has("rate_gap_bp"):
        sec["정책"] = f"한미 기준금리차 {t.lvl('rate_gap_bp'):.0f}bp" + \
                     (" (한국이 더 낮음) → 한국은행 인하 여력에 환율 제약 요인." if t.lvl("rate_gap_bp") < 0 else ".")
    return o


def _flags(t, o, cols):
    hi, lo = [], []
    for c in cols:
        if not t.has(c):
            continue
        dv, sg = t.d(c), t.sigma(c)
        if not math.isnan(sg) and sg > 0 and abs(dv) > SIGMA_K * sg:
            u = {"원": "원", "idx": "%", "pt": "pt"}.get(NAMES[c][1], "bp")
            o["flags"].append(("⚡", f"{NAMES[c][0]} {_bp(dv, u)} — 평소 하루 변동폭(1σ≈{sg:.1f}{u})의 {abs(dv) / sg:.1f}배, 이례적 변동"))
        p = t.pct(c)
        win = t.df[c].iloc[max(0, t.i - WINDOW + 1): t.i + 1].dropna()
        if math.isnan(p) or win.nunique() < 10:   # 기준금리처럼 거의 안 변하는 지표는 고점/저점 판단 제외
            continue
        if p >= HI_PCT:
            hi.append(f"{NAMES[c][0]} {_lvl(c, t.lvl(c))}({p:.0f})")
        elif p <= LO_PCT:
            lo.append(f"{NAMES[c][0]} {_lvl(c, t.lvl(c))}({p:.0f})")
    if hi:
        o["flags"].append(("▲", "1년 고점권: " + ", ".join(hi)))
    if lo:
        o["flags"].append(("▼", "1년 저점권: " + ", ".join(lo)))


RULES = [
    ("판정", "보합", "금리 ±1bp, 회사채 스프레드·환율 ±2(bp·원) 미만이면 방향 없음"),
    ("판정", "이례적 변동 ⚡", "오늘 변화 > 최근 1년 일간 변화 표준편차 × 2"),
    ("판정", "고점권 ▲ / 저점권 ▼", "1년 중 위치 90 이상 / 10 이하"),
    ("판정", "추세", "최근 5영업일 누적과 오늘 방향이 같으면 지속, 반대면 되돌림"),
    ("U1", "불 스티프닝", "2Y·10Y 하락, 2Y가 더 하락 → 연준 인하 기대 확대"),
    ("U2", "불 플래트닝", "2Y·10Y 하락, 10Y가 더 하락 → 경기 둔화 우려·안전자산 수요"),
    ("U3", "베어 플래트닝", "2Y·10Y 상승, 2Y가 더 상승 → 긴축·인하 지연 기대"),
    ("U4", "베어 스티프닝", "2Y·10Y 상승, 10Y가 더 상승 → 물가·재정 우려, 기간 프리미엄 상승"),
    ("U5", "트위스트", "2Y와 10Y가 반대 방향"),
    ("U6", "금리 분해", "10년 변화 = 실질금리(TIPS) 변화 + 기대인플레(BEI) 변화. 더 큰 쪽이 '주도 요인'"),
    ("U7", "정책 기대 갭", "2Y − 기준금리 중간값. 더 마이너스 → 인하 기대 강화. −25bp마다 대략 1회 인하 반영으로 환산(근사)"),
    ("U8", "글로벌 Risk-off/on", "미 국채↓ + HY 스프레드↑ → Risk-off / 미 국채↑ + HY↓ → Risk-on"),
    ("U9", "미국 등급 차별화", "HY − IG 확대"),
    ("U10", "커브 역전", "2s10s·10Y−3M의 신규 역전, 역전 지속, 역전 해소 표시"),
    ("U11", "한미 금리차", "한−미 10년 금리차 하락(한국이 상대적으로 낮아짐) → 외국인 채권 유출·원화 약세 요인"),
    ("U12", "동조화", "미 10년 2σ 변동 다음 날 한국 10년 반응, 최근 120일 동조화 계수 β(미국 1bp당 한국 반응)"),
    ("U13", "변동성·크레딧", "VIX(±1pt 이상)와 HY 스프레드(±2bp 이상) 동반 상승 → Risk-off 확인. VIX 20~30 경계, 30 이상 공포 구간"),
    ("U14", "주식·크레딧 괴리", "5일간 S&P 500 +1% 이상인데 HY +10bp 이상 → 크레딧 선행 경고 / S&P 500 −3% 이하인데 HY ±10bp 미만 → 주식 단독 조정"),
]

DAILY_CSS = """
  :root { --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3; --accent:#4dabf7; }
  * { box-sizing:border-box; } body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; background:var(--bg); color:var(--fg); line-height:1.65; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 16px 64px; } a { color:var(--accent); text-decoration:none; }
  h1 { font-size:24px; margin:8px 0 4px; } h2 { font-size:18px; margin:32px 0 10px; }
  .sub,.muted { color:var(--muted); font-size:13px; } .sub { font-size:14px; margin-bottom:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:12px; }
  .regime { font-size:20px; font-weight:800; margin:2px 0 4px; }
  .tag { display:inline-block; font-size:11px; font-weight:700; color:#0b1015; background:var(--accent); border-radius:4px; padding:0 6px; margin-right:6px; }
  ul { margin:6px 0 0; padding-left:20px; } li { margin:4px 0; font-size:14px; } .sec b { display:inline-block; min-width:48px; }
  details { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 16px; margin-bottom:8px; } summary { cursor:pointer; font-size:14px; }
  table { width:100%; border-collapse:collapse; font-size:13px; } td { border-top:1px solid var(--line); padding:7px 6px; vertical-align:top; }
  td:first-child { color:var(--muted); white-space:nowrap; width:48px; } td:nth-child(2) { font-weight:700; white-space:nowrap; }
"""


def _lst(title, items, kind="plain"):
    """kind: 'tag' (규칙번호, 문장) / 'icon' (아이콘, 문장) / 'plain' (문장)"""
    if not items:
        return ""
    if kind == "tag":
        body = "".join(f'<li><span class="tag">{s[0]}</span>{s[1]}</li>' for s in items)
    elif kind == "icon":
        body = "".join(f"<li>{a} {b}</li>" for a, b in items)
    else:
        body = "".join(f"<li>{x}</li>" for x in items)
    return f'<div class="muted" style="margin-top:12px">{title}</div><ul>{body}</ul>'


def _signals_with_charts(signals, frame, df):
    """오늘 카드용: 신호마다 관련 지표 작은 그래프(같은 지표 조합은 한 번만)."""
    if not signals:
        return ""
    items, seen = [], set()
    for s in signals:
        g = ""
        if len(s) > 2 and tuple(s[2]) not in seen:
            seen.add(tuple(s[2]))
            g = minichart.canvas(minichart.chart(frame, df, s[2], NAMES))
        items.append(f'<li><span class="tag">{s[0]}</span>{s[1]}{g}</li>')
    return '<div class="muted" style="margin-top:12px">해석 신호</div><ul>' + "".join(items) + "</ul>"


def _block_us(r, full=True, df=None):
    h = ""
    if r.get("regime"):
        h += f'<div class="muted">커브 국면 (2년·10년)</div><div class="regime">{r["regime"]}</div><div>{r["regime_why"]}</div>'
        if r.get("regime5"):
            h += f'<div class="muted" style="margin-top:4px">최근 5영업일 기준: {r["regime5"]}</div>'
    if r["facts"]:
        h += "<ul>" + "".join(f"<li>{x}</li>" for x in r["facts"]) + "</ul>"
    if full and df is not None:
        h += minichart.canvas(minichart.chart("US", df, ["ust2", "ust10", "s2s10_bp"], NAMES), height=190)
        h += _signals_with_charts(r["signals"], "US", df) or \
            '<div class="muted" style="margin-top:12px">해석 신호: 뚜렷한 신호 없음</div>'
    else:
        h += _lst("해석 신호", r["signals"], "tag") or '<div class="muted" style="margin-top:12px">해석 신호: 뚜렷한 신호 없음</div>'
    h += _lst("주목할 수치", r["flags"], "icon")
    if full:
        h += _lst("5일 추세", r.get("trends", []))
    return h


def _block_kr(r, df=None):
    h = ("<ul>" + "".join(f"<li>{x}</li>" for x in r["facts"]) + "</ul>") if r["facts"] else ""
    if df is not None:
        h += minichart.canvas(minichart.chart("KUS", df, ["ktb10", "ust10_k", "kr_us10_bp"], NAMES), height=190)
        h += _signals_with_charts(r["signals"], "KUS", df)
    else:
        h += _lst("해석 신호", r["signals"], "tag")
    h += _lst("주목할 수치", r["flags"], "icon")
    if r["sector"]:
        h += '<div class="muted" style="margin-top:12px">시사점</div><ul class="sec">' + \
             "".join(f"<li><b>{a}</b> {b}</li>" for a, b in r["sector"].items()) + "</ul>"
    return h


def render_daily(us, k, built):
    idx = list(range(max(1, len(us) - HISTORY_N), len(us)))
    res = [interpret_us(Day(us, i)) for i in idx][::-1]
    kr_today = interpret_kr(Day(k, len(k) - 1), k)
    kc = k.drop(columns=["us_src"], errors="ignore")   # 그래프용(숫자 컬럼만)
    hist = "".join(f'<details><summary><b>{r["date"]}</b> · {r.get("regime") or "-"} · 신호 {len(r["signals"])}개'
                   f'{" · ⚡" if any(a == "⚡" for a, _ in r["flags"]) else ""}</summary>'
                   f'<div style="margin-top:8px">{_block_us(r, False)}</div></details>' for r in res[1:])
    rules = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in RULES)
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>미국 오늘의 해석</title><style>{DAILY_CSS}{minichart.CSS}</style></head>
<body><div class="wrap">
  <div><a href="us.html">← 🇺🇸 미국 대시보드</a> · <a href="daily.html">🧭 한국 오늘의 해석</a> · <a href="guide.html#us">📘 지표 가이드</a></div>
  <h1>🧭 미국 오늘의 해석</h1>
  <div class="sub">미국 기준일 <b>{res[0]["date"]}</b> · 한미 비교 기준일 <b>{kr_today["date"]}</b> · 페이지 생성 {built}</div>
  <h2 style="margin-top:8px">🇺🇸 미국 시장</h2>
  <div class="card">{_block_us(res[0], True, us)}</div>
  <h2>🇰🇷🇺🇸 한미 연결</h2>
  <div class="card">{_block_kr(kr_today, kc) or '<div class="muted">데이터 없음</div>'}</div>
  <div class="muted">⚠️ 숫자의 움직임이 보내는 '신호'를 규칙대로 읽은 것이에요. 원인(FOMC, CPI·고용지표, 유가, 재정 이슈 등)은 그날 뉴스와 맞춰 확인하세요.</div>
  <h2>최근 {len(res) - 1}거래일 미국 해석 기록</h2>{hist}
  <h2 id="rules">해석 기준</h2><div class="card"><table>{rules}</table></div>
  <p class="muted">개인 학습용 자동 해석이며 투자 권유가 아닙니다.</p>
</div>{minichart.script({"US": us, "KUS": kc})}</body></html>"""


def main():
    if not os.path.exists(D("data", "us.csv")):
        print("data/us.csv 없음 → 미국 페이지 건너뜀")
        return
    us, k = load()
    built = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    os.makedirs(D("docs"), exist_ok=True)
    data = json.dumps({"U": payload(us), "K": payload(k.drop(columns=["us_src"]))}, ensure_ascii=False)
    with open(D("docs", "us.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", data).replace("__TABS__", TABS_JS).replace("__BUILT__", built))
    with open(D("docs", "us-daily.html"), "w", encoding="utf-8") as f:
        f.write(render_daily(us, k, built))
    print(f"미국 페이지 생성: docs/us.html, docs/us-daily.html (미국 최신 {us.index.max().date()}, 한미 최신 {k.index.max().date()})")
    try:
        import markets
        markets.build(built)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 증시 페이지 생성 실패: {e}")
    import pwa
    pwa.finalize(D("docs"))


if __name__ == "__main__":
    main()
