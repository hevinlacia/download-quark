#!/usr/bin/env python3
# quark_monitor.py -- 夸克下载 web 控制面板
# 监控下载进度 + 配置下载目录/Cookie + 从网页启动下载
#
# 用法: python3 quark_monitor.py [默认目录] [端口]
#   默认目录: 无配置时监控的目录(可在网页改)。默认端口 7788
#   浏览器打开 http://localhost:7788
import os, sys, json, time, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

args = [a for a in sys.argv[1:] if not a.startswith("-")]
DEFAULT_DIR = os.path.abspath(args[0]) if args else os.getcwd()
PORT = 7788
for a in sys.argv[1:]:
    if a.isdigit():
        PORT = int(a)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.expanduser("~/.config/downloader/config.json")
_state = {}


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def watch_dir():
    return load_config().get("outdir") or DEFAULT_DIR


def fmt(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def scan():
    wd = watch_dir()
    active = []
    try:
        entries = os.listdir(wd)
    except OSError:
        entries = []
    for e in entries:
        if not (e.startswith(".") and e.endswith(".parts")):
            continue
        full = os.path.join(wd, e)
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
    hp = os.path.join(wd, ".quark_history.jsonl")
    if os.path.exists(hp):
        try:
            with open(hp) as f:
                lines = f.readlines()[-30:]
            history = [json.loads(l) for l in lines if l.strip()]
        except Exception:
            pass
    history.reverse()
    return active, history, wd


def start_download(fids_str):
    fids = fids_str.split()
    if not fids:
        return False, "缺少 fid"
    cfg = load_config()
    outdir = cfg.get("outdir") or DEFAULT_DIR
    cookie = cfg.get("cookie", "")
    if not cookie:
        return False, "未配置 Cookie，请先在设置里填入"
    os.makedirs(outdir, exist_ok=True)
    env = dict(os.environ, OUTDIR=outdir, QUARK_COOKIE=cookie)
    logf = os.path.join(outdir, f"dl_{fids[0][:8]}.log")
    subprocess.Popen(
        [sys.executable, os.path.join(SCRIPT_DIR, "quark_dl.py")] + fids,
        env=env, stdout=open(logf, "a"), stderr=subprocess.STDOUT,
        start_new_session=True)
    return True, f"已启动 {len(fids)} 个文件 -> {outdir}"


HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>夸克下载</title>
<style>
  *{box-sizing:border-box}
  body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:20px;max-width:860px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#888;font-size:13px;margin-bottom:18px;word-break:break-all}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
  @media(max-width:640px){.grid{grid-template-columns:1fr}}
  .card{background:#1a1d24;border-radius:10px;padding:16px 18px;border:1px solid #262a33}
  .card h3{margin:0 0 12px;font-size:14px;color:#9aa0aa;font-weight:600}
  input,textarea{width:100%;background:#0f1115;border:1px solid #2a2f3a;border-radius:6px;color:#e6e6e6;padding:8px 10px;font-size:13px;font-family:inherit;margin-bottom:8px}
  textarea{resize:vertical;min-height:54px}
  button{background:#3b82f6;color:#fff;border:0;border-radius:6px;padding:8px 16px;font-size:13px;cursor:pointer;font-weight:600}
  button:hover{background:#2563eb}
  button.sec{background:#262a33}
  button.sec:hover{background:#313644}
  .msg{font-size:12px;margin-top:6px;min-height:16px}
  .ok{color:#22c55e}.err{color:#ef4444}
  .fname{font-weight:600;font-size:15px;margin-bottom:10px;word-break:break-all}
  .bar{height:10px;background:#2a2f3a;border-radius:5px;overflow:hidden;margin-bottom:8px}
  .bar>div{height:100%;background:linear-gradient(90deg,#3b82f6,#06b6d4);transition:width .4s}
  .row{display:flex;justify-content:space-between;font-size:13px;color:#9aa0aa;margin-top:4px}
  .row b{color:#e6e6e6}
  h2{font-size:14px;color:#9aa0aa;margin:18px 0 8px;font-weight:600}
  .hist{font-size:13px;color:#9aa0aa;padding:6px 0;border-bottom:1px solid #1f232b}
  .empty{color:#555;text-align:center;padding:36px 0}
  .pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px;animation:p 1.5s infinite}
  @keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
</style></head><body>
<h1><span class="pulse"></span>夸克下载</h1>
<div class="sub" id="dir"></div>

<div class="grid">
  <div class="card">
    <h3>⚙️ 设置</h3>
    <input id="outdir" placeholder="下载目录, 如 /home/hevin/下载/网盘">
    <textarea id="cookie" placeholder="夸克网盘完整 Cookie (留空则不变)"></textarea>
    <button onclick="saveCfg()">保存</button>
    <div class="msg" id="cfgmsg"></div>
  </div>
  <div class="card">
    <h3>➕ 新建下载</h3>
    <textarea id="fids" placeholder="粘贴文件 fid (多个用空格或换行分隔)"></textarea>
    <button onclick="startDl()">开始下载</button>
    <div class="msg" id="dlmsg"></div>
  </div>
</div>

<h2>进行中</h2>
<div id="active"></div>
<h2 id="hh" style="display:none">历史</h2>
<div id="history"></div>

<script>
function gb(b){return (b/1073741824).toFixed(2)+' GB';}
function mb(b){return (b/1048576).toFixed(1)+' MB';}
function eta(s){if(s<0||s>999999)return '--';if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60),r=Math.round(s%60);return m+'m'+String(r).padStart(2,'0')+'s';}
function dur(s){if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60);return m+'m';}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

async function loadCfg(){
  const d=await(await fetch('/config')).json();
  document.getElementById('outdir').value=d.outdir||'';
  document.getElementById('cookie').placeholder=d.has_cookie?'已配置 (如需更新请粘贴新 Cookie，留空不变)':'夸克网盘完整 Cookie';
}
async function saveCfg(){
  const outdir=document.getElementById('outdir').value.trim();
  const cookie=document.getElementById('cookie').value;
  const body={outdir};
  if(cookie.trim()) body.cookie=cookie;
  const r=await fetch('/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  const m=document.getElementById('cfgmsg');
  m.textContent=d.ok?('✅ 已保存，监控目录: '+(d.outdir||'(默认)')):('❌ '+(d.error||'保存失败'));
  m.className='msg '+(d.ok?'ok':'err');
  document.getElementById('cookie').value='';
  if(d.ok) tick();
}
async function startDl(){
  const fids=document.getElementById('fids').value.trim();
  if(!fids){const m=document.getElementById('dlmsg');m.textContent='❌ 请填入 fid';m.className='msg err';return;}
  const r=await fetch('/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fid:fids})});
  const d=await r.json();
  const m=document.getElementById('dlmsg');
  m.textContent=d.ok?('✅ '+d.info):('❌ '+(d.error||'启动失败'));
  m.className='msg '+(d.ok?'ok':'err');
  if(d.ok){document.getElementById('fids').value='';setTimeout(tick,1500);}
}
async function tick(){
  try{
    const d=await(await fetch('/status')).json();
    document.getElementById('dir').textContent='监控目录: '+(d.dir||'');
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
      `<div class="hist">${y.ok?'<span style="color:#22c55e">✅</span>':'<span style="color:#ef4444">❌</span>'} ${esc(y.name)} · ${gb(y.size)} · ${mb(y.avg_speed)}/s · ${dur(y.duration)}</div>`).join('');}
    else{hh.style.display='none';h.innerHTML='';}
  }catch(e){console.error(e);}
}
loadCfg();tick();setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            active, history, wd = scan()
            self._json(200, {"active": active, "history": history, "dir": wd})
        elif self.path == "/config":
            cfg = load_config()
            self._json(200, {"outdir": cfg.get("outdir", ""),
                            "has_cookie": bool(cfg.get("cookie"))})
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            data = {}
        if self.path == "/config":
            cfg = load_config()
            if "outdir" in data:
                cfg["outdir"] = (data.get("outdir") or "").strip()
            if data.get("cookie"):
                cfg["cookie"] = data["cookie"].strip()
            save_config(cfg)
            self._json(200, {"ok": True, "outdir": cfg.get("outdir", "")})
        elif self.path == "/download":
            ok, info = start_download(data.get("fid", ""))
            self._json(200 if ok else 400, {"ok": ok, "info": info} if ok else {"ok": False, "error": info})
        else:
            self._json(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"夸克下载控制面板  http://localhost:{PORT}")
    print(f"默认目录: {DEFAULT_DIR}  (可在网页配置)")
    print(f"配置文件: {CONFIG_PATH}")
    print("Ctrl+C 退出")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
