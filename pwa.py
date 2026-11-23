"""
PWA(설치형 웹앱) 설정: docs/ 에 manifest.json · sw.js · 아이콘을 만들고, 모든 페이지에 설치 정보를 넣음.
build_dashboard.py, build_us.py 마지막에 finalize()가 호출됨 (여러 번 실행돼도 안전).
"""
import glob
import json
import os
import struct
import zlib

APP_NAME = "NOIS"
SHORT_NAME = "NOIS"
BG = (15, 20, 25)            # #0f1419
MARK = "<!--pwa-->"

MANIFEST = {
    "name": APP_NAME,
    "short_name": SHORT_NAME,
    "description": "한국·미국 금리·크레딧 스프레드 일별 대시보드와 규칙 기반 해석",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "background_color": "#0f1419",
    "theme_color": "#0f1419",
    "lang": "ko",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
    "shortcuts": [
        {"name": "오늘의 해석", "url": "./daily.html"},
        {"name": "미국 대시보드", "url": "./us.html"},
        {"name": "미국 오늘의 해석", "url": "./us-daily.html"},
    ],
}

# 서비스워커: 항상 최신 데이터를 먼저 받고(network-first), 인터넷이 없으면 마지막으로 본 화면을 보여줌
SW = """const CACHE = "rate-dashboard-v1";
const CORE = ["./", "./index.html", "./daily.html", "./us.html", "./us-daily.html", "./guide.html", "./manifest.json", "./icon-192.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {}); return r;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
"""

HEAD = f"""{MARK}
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#0f1419">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{APP_NAME}">
"""

# 안드로이드 크롬: 설치 가능할 때만 '앱 설치' 버튼을 띄움 (아이폰은 Safari 공유 → 홈 화면에 추가)
BODY = """<script>
if ("serviceWorker" in navigator) { navigator.serviceWorker.register("sw.js").catch(() => {}); }
let _pwaEvt = null;
window.addEventListener("beforeinstallprompt", e => {
  e.preventDefault(); _pwaEvt = e;
  if (document.getElementById("pwaBtn")) return;
  const b = document.createElement("button"); b.id = "pwaBtn"; b.textContent = "📱 앱 설치";
  b.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:99;background:#4dabf7;color:#0b1015;border:none;border-radius:999px;padding:10px 16px;font-weight:700;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.4);cursor:pointer";
  b.onclick = async () => { b.remove(); _pwaEvt.prompt(); _pwaEvt = null; };
  document.body.appendChild(b);
});
</script>
"""


# ---------------------------------------------------------------------------
# 아이콘: 외부 패키지 없이 PNG 직접 생성 (어두운 배경 + 상승 막대 3개 + 흰 꺾은선)
# ---------------------------------------------------------------------------
def _png(w, h, rows):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _icon(size):
    s = size / 512
    px = [[list(BG) for _ in range(size)] for _ in range(size)]

    def rect(x0, y0, x1, y1, col):
        for y in range(max(0, int(y0 * s)), min(size, int(y1 * s))):
            for x in range(max(0, int(x0 * s)), min(size, int(x1 * s))):
                px[y][x] = list(col)

    # 막대 (안전 영역 안쪽: maskable 대비 가장자리 여백)
    rect(130, 290, 190, 380, (77, 171, 247))    # 파랑
    rect(226, 230, 286, 380, (255, 169, 77))    # 주황
    rect(322, 170, 382, 380, (105, 219, 124))   # 초록
    rect(118, 392, 394, 402, (139, 149, 163))   # 바닥선
    # 꺾은선 (두께 있는 선)
    pts = [(140, 250), (230, 200), (290, 215), (380, 130)]
    r = 9 * s
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        n = int(max(abs(xb - xa), abs(yb - ya)) * s) + 1
        for i in range(n + 1):
            cx, cy = (xa + (xb - xa) * i / n) * s, (ya + (yb - ya) * i / n) * s
            for y in range(int(cy - r), int(cy + r) + 1):
                for x in range(int(cx - r), int(cx + r) + 1):
                    if 0 <= x < size and 0 <= y < size and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                        px[y][x] = [230, 233, 238]
    return _png(size, size, [sum(row, []) for row in px])


def write_assets(docs):
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
    with open(os.path.join(docs, "sw.js"), "w", encoding="utf-8") as f:
        f.write(SW)
    for n in (192, 512):
        p = os.path.join(docs, f"icon-{n}.png")
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(_icon(n))


def inject(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    if MARK in html:
        return
    html = html.replace("</head>", HEAD + "</head>", 1)
    i = html.rfind("</body>")
    html = html[:i] + BODY + html[i:] if i >= 0 else html + BODY
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def finalize(docs):
    write_assets(docs)
    for p in glob.glob(os.path.join(docs, "*.html")):
        inject(p)
    print("PWA 설정 완료: manifest.json, sw.js, 아이콘")


if __name__ == "__main__":
    finalize(os.path.join(os.path.dirname(__file__), "docs"))
