"""
🎤 30초 브리핑 (면접 시황 질문 대비)

규칙으로 만든 3문장 + 기관별 한 줄.
  1문장: 금리 — 국고 3·10년 수준·변화와 커브 국면
  2문장: 크레딧·자금시장 — 오늘 가장 강한 신호(없으면 스프레드 수준)
  3문장: 다음 변수 — 가장 가까운 이벤트
  기관별: 신호등 + 점수 기여가 가장 큰 항목의 '해석' 부분
"""
import datetime as dt
import re

import events

SHORT_WHY = {
    "불 스티프닝": "기준금리 인하 기대가 커지는 모습",
    "불 플래트닝": "경기 둔화 우려나 장기채 수요가 반영된 모습",
    "베어 플래트닝": "인상 기대(또는 인하 기대 후퇴)가 반영된 모습",
    "베어 스티프닝": "물가·재정 우려나 해외 금리 영향이 반영된 모습",
    "트위스트": "단기 정책 기대와 장기 전망이 엇갈리는 모습",
}
INST = {"capital": "캐피탈", "insurance": "보험", "bank": "은행"}


def _ieyo(word):
    """받침 있으면 '이에요', 없으면 '예요' (괄호로 끝나면 괄호 앞 글자 기준)."""
    ch = word.rstrip(")")[-1]
    if "가" <= ch <= "힣":
        return "이에요" if (ord(ch) - 0xAC00) % 28 else "예요"
    return "예요"


def _regime_name(reg):
    for k in SHORT_WHY:
        if reg and k in reg:
            return k
    return None


def _interp(text):
    m = re.search(r"`해석`\s*(.+)$", text)
    return m.group(1).strip() if m else re.sub(r"`[^`]+`\s*", "", text)


def make(today_res: dict, inst: dict, day: dt.date):
    f = today_res["facts"][0] if today_res["facts"] else ""
    m = re.search(r"국고 3년 ([\d.]+)% \(([^)]+)\), 10년 ([\d.]+)% \(([^)]+)\)", f)
    rn = _regime_name(today_res.get("regime"))
    if m:
        s1 = f"국고 3년 {float(m.group(1)):.2f}%({m.group(2)}), 10년 {float(m.group(3)):.2f}%({m.group(4)})로"
        s1 += f" {rn} — {SHORT_WHY[rn]}이에요." if rn else " 큰 방향 없이 보합이에요."
    else:
        s1 = "오늘 국고채 데이터가 충분하지 않아요."
    sig = [t for tag, t, _ in today_res["signals"] if tag not in ("R1", "R2", "R3", "R4", "R5")]
    if sig:
        s2 = re.sub(r"\s*\(.*?\)\s*$", "", sig[0].split(". ")[0]).rstrip(".") + "."
        s2 = s2.replace("→", "—")
    else:
        s2 = "크레딧·단기자금 쪽에는 규칙에 걸린 뚜렷한 신호가 없었어요."
    up = events.upcoming(30, day)
    nxt = [e for e in up if e["kr"] > day] or up
    if nxt:
        k = nxt[0]["kind"]
        s3 = f"다음 변수는 {nxt[0]['date']:%m/%d} {k}{_ieyo(k)}."
    else:
        s3 = ""
    lines = []
    for key, (icon, word, total, items) in inst.items():
        if not items:
            continue
        best = max(items, key=lambda x: (abs(x[1]), x[1] != 0))
        lines.append(f"{icon} <b>{INST[key]}</b> {word}({total:+d}) — {_interp(best[2])}")
    return [s1, s2, s3], lines


def section(today_res: dict, inst: dict, day: dt.date) -> str:
    sents, lines = make(today_res, inst, day)
    text = " ".join(s for s in sents if s)
    li = "".join(f"<li>{x}</li>" for x in lines)
    return f"""<h2 id="brief">🎤 30초 브리핑 <span class="muted" style="font-size:13px;font-weight:400">면접 시황 질문 대비</span></h2>
<div class="card">
  <div id="brieftext" style="font-size:15px;line-height:1.75">{text}</div>
  <ul style="margin:10px 0 0;padding-left:18px;font-size:13.5px">{li}</ul>
  <button onclick="navigator.clipboard.writeText(document.getElementById('brieftext').innerText).then(()=>this.textContent='복사됨 ✓')"
    style="margin-top:10px;background:#1f2731;color:#e6e9ee;border:1px solid #2a323d;border-radius:8px;padding:6px 12px;cursor:pointer">문장 복사</button>
  <div class="as">규칙으로 자동 조립한 문장이에요. 면접에서는 그날 뉴스(원인)를 한 줄 덧붙이면 완성돼요.</div>
</div>"""
