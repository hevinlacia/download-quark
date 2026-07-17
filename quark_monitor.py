#!/usr/bin/env python3
# quark_monitor.py -- 夸克下载 web 监控仪表盘
# 扫描下载目录的 .X.parts/.meta.json，实时显示进度。与下载进程解耦，互不影响。
#
# 用法: python3 quark_monitor.py [下载目录] [端口]
#   默认目录=当前目录, 默认端口=7788
# 然后浏览器打开 http://localhost:7788
import os, sys, json, time
from http.server import HTTPServer, BaseHTTPRequestHandler

args = [a for a in sys.argv[1:] if not a.startswith("-")]
WATCH_DIR = os.path.abspath(args[0]) if args else os.getcwd()
PORT = 7788
for a in sys.argv[1:]:
    if a.isdigit():
        PORT = int(a)

_state = {}  # partdir -> [last_bytes, last_time]


def fmt(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def scan():
    active = []
    try:
        entries = os.listdir(WATCH_DIR)
    except OSError:
        entries = []
    for e in entries:
        if not (e.startswith(".") and e.endswith(".parts")):
            continue
        full = os.path.join(WATCH_DIR, e)
        if not os.path.isdir(full):
            continue
        mp = os.path.join(full, ".meta.json")
        if not os.path.exists(mp):
            continue
        try:
            with open(mp) as f:
                meta = json.load(f)
        except Exception:
            continue
        name = meta.get("name", "?")
        size = int(meta.get("size", 0))
        nchunks = int(meta.get("nchunks", 0))
        cur = 0
        for j in range(nchunks):
            try:
                cur += os.path.getsize(os.path.join(full, f"p_{j:05d}"))
            except OSError:
                pass
        now = time.time()
        lb, lt = _state.get(full, [cur, now])
        dt = now - lt
        speed = (cur - lb) / dt if dt > 0 else 0
        _state[full] = [cur, now]
        pct = cur / size * 100 if size else 0
        eta = (size - cur) / speed if speed > 0 else -1
        active.append({
            "name": name, "size": size, "downloaded": cur, "pct": round(pct, 1),
            "speed": speed, "eta": eta, "nchunks": nchunks,
            "done_chunks": int(pct / 100 * nchunks) if nchunks else 0,
            "started": meta.get("started", now),
        })
    active.sort(key=lambda x: x["started"])
    history = []
    hp = os.path.join(WATCH_DIR, ".quark_history.jsonl")
    if os.path.exists(hp):
        try:
            with open(hp) as f:
                lines = f.readlines()[-30:]
            history = [json.loads(l) for l in lines if l.strip()]
        except Exception:
            pass
    history.reverse()
    return active, history


HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>夸克下载监控</title>
<style>
  *{box-sizing:border-box}
  body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:24px;max-width:820px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#888;font-size:13px;margin-bottom:22px;word-break:break-all}
  .card{background:#1a1d24;border-radius:10px;padding:16px 18px;margin-bottom:12px;border:1px solid #262a33}
  .fname{font-weight:600;font-size:15px;margin-bottom:10px;word-break:break-all}
  .bar{height:10px;background:#2a2f3a;border-radius:5px;overflow:hidden;margin-bottom:8px}
  .bar>div{height:100%;background:linear-gradient(90deg,#3b82f6,#06b6d4);transition:width .4s}
  .row{display:flex;justify-content:space-between;font-size:13px;color:#9aa0aa;margin-top:4px}
  .row b{color:#e6e6e6}
  h2{font-size:14px;color:#9aa0aa;margin:22px 0 8px;font-weight:600}
  .hist{font-size:13px;color:#9aa0aa;padding:6px 0;border-bottom:1px solid #1f232b}
  .ok{color:#22c55e}.fail{color:#ef4444}
  .empty{color:#555;text-align:center;padding:50px 0}
  .pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px;animation:p 1.5s infinite}
  @keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
</style></head><body>
<h1><span class="pulse"></span>夸克下载监控</h1>
<div class="sub" id="dir"></div>
<div id="active"></div>
<h2 id="hh" style="display:none">历史</h2>
<div id="history"></div>
<script>
async function tick(){
  try{
    const d=await(await fetch('/status')).json();
    document.getElementById('dir').textContent='目录: '+d.dir;
    const a=document.getElementById('active');
    if(!d.active.length){a.innerHTML='<div class="empty">当前没有正在下载的任务</div>';}
    else{a.innerHTML=d.active.map(x=>{
      const p=x.pct.toFixed(1);
      return `<div class="card"><div class="fname">${esc(x.name)}</div>
        <div class="bar"><div style="width:${p}%"></div></div>
        <div class="row"><b>${p}%</b><span>${gb(x.downloaded)} / ${gb(x.size)}</span></div>
        <div class="row"><span>实时 ${mb(x.speed)}/s</span><span>ETA ${eta(x.eta)}</span></div>
        <div class="row"><span>${x.done_chunks}/${x.nchunks} 块</span><span></span></div></div>`;
    }).join('');}
    const h=document.getElementById('history'),hh=document.getElementById('hh');
    if(d.history.length){hh.style.display='';h.innerHTML=d.history.map(y=>
      `<div class="hist">${y.ok?'<span class="ok">✅</span>':'<span class="fail">❌</span>'} ${esc(y.name)} · ${gb(y.size)} · ${mb(y.avg_speed)}/s · ${dur(y.duration)}</div>`).join('');}
    else{hh.style.display='none';h.innerHTML='';}
  }catch(e){console.error(e);}
}
function gb(b){return (b/1073741824).toFixed(2)+' GB';}
function mb(b){return (b/1048576).toFixed(1)+' MB';}
function eta(s){if(s<0||s>999999)return '--';if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60),r=Math.round(s%60);return m+'m'+String(r).padStart(2,'0')+'s';}
function dur(s){if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60);return m+'m';}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
tick();setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/status":
            active, history = scan()
            body = json.dumps({"active": active, "history": history, "dir": WATCH_DIR}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())


if __name__ == "__main__":
    print(f"夸克下载监控  http://localhost:{PORT}")
    print(f"监控目录: {WATCH_DIR}")
    print("Ctrl+C 退出")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
