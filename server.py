#!/usr/bin/env python3
# quark_daemon.py -- 夸克下载管理器 (Motrix 风格 web 控制面板)
# 全功能下载管理：任务管理、实时进度、暂停/恢复/取消、配置持久化
#
# 用法: python3 quark_daemon.py [端口]
#   浏览器打开 http://localhost:7788
import os, sys, json, time, uuid, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7788
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.expanduser("~/.config/downloader")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
TASKS_PATH = os.path.join(CONFIG_DIR, "tasks.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

# ============================================================
# 配置 & 任务持久化
# ============================================================
def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_tasks():
    try:
        with open(TASKS_PATH) as f:
            return json.load(f)
    except Exception:
        return []

def save_tasks():
    with open(TASKS_PATH, "w") as f:
        json.dump(_TASKS, f, ensure_ascii=False, indent=2)

# ============================================================
# 任务管理器
# ============================================================
_TASKS = load_tasks()  # 主数据
_TASKS_LOCK = threading.Lock()
_WORKERS = {}  # task_id -> {thread, stop_event}

def _next_id():
    return uuid.uuid4().hex[:12]

def _run_worker(task):
    """在后台线程中执行下载任务。"""
    fid = task["fid"]
    outdir = task["outdir"]
    cfg = load_config()
    cookie = cfg.get("cookie", "")

    def progress_cb(downloaded, total, speed, pct, done, nchunks):
        with _TASKS_LOCK:
            task["downloaded"] = downloaded
            task["speed"] = speed
            task["pct"] = round(pct, 1)
            task["done_chunks"] = done
            task["nchunks"] = nchunks
            # 每 2 秒存一次 (避免频繁写)
            if int(time.time()) % 2 == 0:
                save_tasks()

    worker = _WORKERS.get(task["id"])
    stop_event = worker["stop_event"] if worker else threading.Event()

    try:
        from engine import download_task
        ok, name, err = download_task(fid, outdir=outdir, cookie=cookie,
                                       progress_cb=progress_cb, stop_event=stop_event)
        with _TASKS_LOCK:
            if stop_event.is_set():
                task["status"] = "paused" if task.get("status") != "cancelled" else "cancelled"
            elif ok:
                task["status"] = "completed"
                task["pct"] = 100
                task["downloaded"] = task["size"]
                task["completed_at"] = time.time()
            else:
                task["status"] = "failed"
                task["error"] = err
    except Exception as e:
        with _TASKS_LOCK:
            task["status"] = "failed"
            task["error"] = str(e)
    finally:
        with _TASKS_LOCK:
            save_tasks()
        _WORKERS.pop(task["id"], None)

def start_worker(task):
    """启动任务的后台工作线程。"""
    if task["id"] in _WORKERS:
        return
    stop_event = threading.Event()
    _WORKERS[task["id"]] = {"stop_event": stop_event}
    t = threading.Thread(target=_run_worker, args=(task,), daemon=True)
    t.start()

def create_task(fid, outdir=None):
    """创建新任务并启动下载。"""
    cfg = load_config()
    if not cfg.get("cookie"):
        return None, "未配置 Cookie，请先在设置里填入"
    od = outdir or cfg.get("outdir") or os.getcwd()
    os.makedirs(od, exist_ok=True)

    task = {
        "id": _next_id(),
        "type": "quark",
        "fid": fid.strip(),
        "name": fid[:8] + "...",
        "size": 0,
        "downloaded": 0,
        "speed": 0,
        "pct": 0,
        "status": "active",
        "error": None,
        "created_at": time.time(),
        "completed_at": None,
        "outdir": od,
        "outfile": "",
        "nchunks": 0,
        "done_chunks": 0,
    }
    with _TASKS_LOCK:
        _TASKS.insert(0, task)
        save_tasks()
    start_worker(task)
    return task, None

def pause_task(tid):
    """暂停任务。"""
    with _TASKS_LOCK:
        task = next((t for t in _TASKS if t["id"] == tid), None)
        if not task or task["status"] != "active":
            return False, "只能暂停进行中的任务"
        task["status"] = "paused"
        save_tasks()
    w = _WORKERS.get(tid)
    if w:
        w["stop_event"].set()
    return True, None

def resume_task(tid):
    """恢复被暂停的任务（创建新工作线程，利用 .parts 续传）。"""
    with _TASKS_LOCK:
        task = next((t for t in _TASKS if t["id"] == tid), None)
        if not task or task["status"] != "paused":
            return False, "只能恢复已暂停的任务"
        task["status"] = "active"
        task["error"] = None
        save_tasks()
    start_worker(task)
    return True, None

def cancel_task(tid):
    """取消任务（停止下载，保留 .parts 但标记取消）。"""
    with _TASKS_LOCK:
        task = next((t for t in _TASKS if t["id"] == tid), None)
        if not task:
            return False, "任务不存在"
        task["status"] = "cancelled"
        save_tasks()
    w = _WORKERS.get(tid)
    if w:
        w["stop_event"].set()
    return True, None

def remove_task(tid):
    """删除任务记录（可同时清理 .parts）。"""
    cancel_task(tid)
    with _TASKS_LOCK:
        _TASKS[:] = [t for t in _TASKS if t["id"] != tid]
        save_tasks()
    return True, None

# 启动时：恢复之前 active 的任务为 paused（worker 已死）
for t in _TASKS:
    if t["status"] in ("active",):
        t["status"] = "paused"
save_tasks()

# ============================================================
# HTTP 服务器
# ============================================================
class ThreadingServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def api_json(handler, code, obj):
    body = json.dumps(obj, ensure_ascii=False).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(body)


def parse_path(path):
    """解析路径，返回 (parts: list, id: str|None, action: str|None)。"""
    parts = [p for p in path.split("/") if p]
    tid = None
    action = None
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "tasks":
        tid = parts[2]
        action = parts[3] if len(parts) > 3 else None
    return parts, tid, action


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        parts, tid, _ = parse_path(self.path)
        if self.path == "/api/tasks":
            with _TASKS_LOCK:
                api_json(self, 200, {"tasks": list(_TASKS)})
        elif self.path == "/api/settings":
            cfg = load_config()
            api_json(self, 200, {"outdir": cfg.get("outdir", ""), "has_cookie": bool(cfg.get("cookie"))})
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        else:
            api_json(self, 404, {"error": "not found"})

    def do_POST(self):
        parts, tid, action = parse_path(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            data = {}

        # /api/settings
        if self.path == "/api/settings":
            cfg = load_config()
            if "outdir" in data:
                cfg["outdir"] = (data.get("outdir") or "").strip()
            if data.get("cookie"):
                cfg["cookie"] = data["cookie"].strip()
            save_config(cfg)
            api_json(self, 200, {"ok": True, "outdir": cfg.get("outdir", "")})

        # POST /api/tasks
        elif self.path == "/api/tasks":
            fid = (data.get("fid") or "").strip()
            if not fid:
                api_json(self, 400, {"ok": False, "error": "缺少 fid"})
                return
            fids = fid.split()
            results = []
            for f in fids:
                task, err = create_task(f)
                results.append({"fid": f, "ok": err is None, "task_id": task["id"] if task else None, "error": err})
            api_json(self, 200 if all(r["ok"] for r in results) else 207, {"results": results})

        # POST /api/tasks/:id/:action
        elif len(parts) == 4 and parts[0] == "api" and parts[1] == "tasks" and tid:
            action_map = {
                "pause": pause_task,
                "resume": resume_task,
                "cancel": cancel_task,
            }
            fn = action_map.get(action)
            if fn:
                ok, err = fn(tid)
                api_json(self, 200 if ok else 400, {"ok": ok, "error": err})
            else:
                api_json(self, 404, {"error": f"unknown action: {action}"})
        else:
            api_json(self, 404, {"error": "not found"})

    def do_DELETE(self):
        parts, tid, _ = parse_path(self.path)
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "tasks" and tid:
            ok, err = remove_task(tid)
            api_json(self, 200 if ok else 400, {"ok": ok, "error": err})
        else:
            api_json(self, 404, {"error": "not found"})


# ============================================================
# 前端 HTML (Motrix 风格)
# ============================================================
HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>夸克下载</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:#0f1115;color:#e6e6e6;display:flex;height:100vh;overflow:hidden}

/* 侧栏 */
.side{width:180px;background:#13161c;border-right:1px solid #1f232b;padding:20px 0;flex-shrink:0;display:flex;flex-direction:column}
.side h1{font-size:15px;padding:0 18px;margin-bottom:20px;font-weight:600;letter-spacing:.5px;color:#e6e6e6}
.side h1 small{display:block;font-size:11px;font-weight:400;color:#555;margin-top:2px}
.side .f{display:block;padding:9px 18px;font-size:13px;color:#9aa0aa;cursor:pointer;border:none;background:0;width:100%;text-align:left;transition:.15s}
.side .f:hover{color:#e6e6e6;background:#1a1d24}
.side .f.act{color:#e6e6e6;background:#1a1d24;border-left:2px solid #3b82f6}
.side .f .c{float:right;color:#555;font-size:12px}
.side .gap{flex:1}
.side .foot{font-size:11px;color:#444;padding:12px 18px;border-top:1px solid #1f232b}

/* 主区 */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.top{display:flex;align-items:center;gap:10px;padding:14px 22px;border-bottom:1px solid #1f232b;flex-shrink:0}
.top .tt{font-size:13px;color:#9aa0aa;flex:1}
.top .btn{background:#3b82f6;color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:13px;cursor:pointer;font-weight:600}
.top .btn:hover{background:#2563eb}
.top .btn2{background:0;border:1px solid #262a33;color:#9aa0aa;border-radius:6px;padding:7px 10px;font-size:13px;cursor:pointer}
.top .btn2:hover{color:#e6e6e6;border-color:#3a4355}

.list{flex:1;overflow-y:auto;padding:14px 18px}

/* 空状态 */
.empty{text-align:center;padding:60px 20px;color:#555}
.empty .big{font-size:48px;margin-bottom:12px}

/* 卡片 */
.card{background:#1a1d24;border-radius:10px;padding:16px 18px;margin-bottom:10px;border:1px solid #262a33;transition:.15s}
.card:hover{border-color:#3a4355}
.card .h{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px}
.card .h .n{font-weight:600;font-size:14px;word-break:break-all;flex:1;min-width:0}
.card .h .b{flex-shrink:0;margin-left:10px;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600}
.b-active{background:#1e3a5f;color:#60a5fa}
.b-paused{background:#2a2f3a;color:#9aa0aa}
.b-completed{background:#1a3a2a;color:#22c55e}
.b-failed{background:#3a1a1a;color:#ef4444}
.b-cancelled{background:#2a2f3a;color:#666}
.bar{height:8px;background:#2a2f3a;border-radius:4px;overflow:hidden;margin-bottom:6px}
.bar>div{height:100%;border-radius:4px;transition:width .4s}
.bar .ok{background:linear-gradient(90deg,#22c55e,#16a34a)}
.bar .go{background:linear-gradient(90deg,#3b82f6,#06b6d4)}
.bar .er{background:linear-gradient(90deg,#ef4444,#dc2626)}
.card .r{display:flex;justify-content:space-between;font-size:12px;color:#9aa0aa;margin-top:2px}
.card .r span{white-space:nowrap}
.card .act{margin-top:8px;display:flex;gap:6px}
.card .act button{background:0;border:1px solid #2a2f3a;color:#9aa0aa;border-radius:5px;padding:4px 10px;font-size:12px;cursor:pointer}
.card .act button:hover{color:#e6e6e6;border-color:#3a4355}
.card .act .d{color:#ef4444}
.card .act .d:hover{border-color:#ef4444}

/* 模态框 */
.modal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.modal.show{display:flex}
.modal .box{background:#1a1d24;border-radius:12px;padding:24px;width:440px;max-width:90%;border:1px solid #262a33}
.modal .box h3{margin:0 0 14px;font-size:15px}
.modal .box label{font-size:12px;color:#9aa0aa;display:block;margin-bottom:4px;margin-top:8px}
.modal .box input,.modal .box textarea{width:100%;background:#0f1115;border:1px solid #2a2f3a;border-radius:6px;color:#e6e6e6;padding:8px 10px;font-size:13px;font-family:inherit;margin-bottom:8px}
.modal .box textarea{resize:vertical;min-height:60px}
.modal .box .btns{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}
.modal .box .btns button{padding:7px 16px;border-radius:6px;border:0;font-size:13px;cursor:pointer;font-weight:600}
.modal .box .btns .pr{background:#3b82f6;color:#fff}
.modal .box .btns .pr:hover{background:#2563eb}
.modal .box .btns .sc{background:#262a33;color:#9aa0aa}
.modal .box .btns .sc:hover{color:#e6e6e6}
.modal .box .err{font-size:12px;color:#ef4444;margin-top:4px;min-height:16px}
.modal .box .ok{font-size:12px;color:#22c55e;margin-top:4px;min-height:16px}
</style></head><body>

<div class="side">
  <h1>下载管理<small>夸克网盘</small></h1>
  <button class="f act" data-f="all" onclick="setF(this)">全部 <span class="c" id="c_all">0</span></button>
  <button class="f" data-f="active" onclick="setF(this)">进行中 <span class="c" id="c_active">0</span></button>
  <button class="f" data-f="completed" onclick="setF(this)">已完成 <span class="c" id="c_completed">0</span></button>
  <button class="f" data-f="failed" onclick="setF(this)">失败 <span class="c" id="c_failed">0</span></button>
  <div class="gap"></div>
  <div class="foot" id="fdir">~</div>
</div>

<div class="main">
  <div class="top">
    <div class="tt" id="ftitle">全部</div>
    <button class="btn2" onclick="loadTasks()" title="刷新">🔄</button>
    <button class="btn2" onclick="showSettings()" title="设置">⚙️</button>
    <button class="btn" onclick="showNew()">+ 新建</button>
  </div>
  <div class="list" id="list"></div>
</div>

<!-- 新建下载弹窗 -->
<div class="modal" id="modalNew">
  <div class="box">
    <h3>新建下载</h3>
    <label>夸克文件 fid（多个用空格/换行分隔）</label>
    <textarea id="inpFid" placeholder="粘贴 fid…"></textarea>
    <div id="newMsg" class="err"></div>
    <div class="btns">
      <button class="sc" onclick="closeModal('modalNew')">取消</button>
      <button class="pr" onclick="startNew()">开始下载</button>
    </div>
  </div>
</div>

<!-- 设置弹窗 -->
<div class="modal" id="modalSet">
  <div class="box">
    <h3>设置</h3>
    <label>下载目录</label>
    <input id="inpOutdir" placeholder="如 /home/hevin/下载/网盘">
    <label>夸克 Cookie</label>
    <textarea id="inpCookie" placeholder="留空则不改变已配置的 Cookie"></textarea>
    <div id="setMsg" class="ok"></div>
    <div class="btns">
      <button class="sc" onclick="closeModal('modalSet')">关闭</button>
      <button class="pr" onclick="saveSettings()">保存</button>
    </div>
  </div>
</div>

<script>
let _filter = 'all';
let _tasks = [];

function gb(b){return b?((b/1073741824).toFixed(2)+' GB'):'0 B';}
function mb(b){return (b/1048576).toFixed(1)+' MB';}
function eta(s){if(s<0||s>999999)return '--';if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60),r=Math.round(s%60);return m+':'+String(r).padStart(2,'0');}
function dur(s){if(s<60)return Math.round(s)+'s';const m=Math.floor(s/60);return m+'m';}
function esc(s){return String(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function statusBadge(s){
  const m={'active':'进行中','paused':'已暂停','completed':'已完成','failed':'失败','cancelled':'已取消'};
  return `<span class="b b-${s}">${m[s]||s}</span>`;
}

function renderCard(t){
  const isActive=t.status==='active',isPaused=t.status==='paused',isDone=t.status==='completed',isFail=t.status==='failed';
  const pct=Math.min(t.pct||0,100);
  const barClass=isDone?'ok':(isFail?'er':'go');
  const actions=[];
  if(isActive) actions.push(`<button onclick="act('${t.id}','pause')">⏸ 暂停</button>`);
  if(isPaused) actions.push(`<button onclick="act('${t.id}','resume')">▶️ 恢复</button>`);
  if(isActive||isPaused) actions.push(`<button class="d" onclick="act('${t.id}','cancel')">✕ 取消</button>`);
  if(isDone||isFail||t.status==='cancelled') actions.push(`<button class="d" onclick="rm('${t.id}')">🗑 删除</button>`);
  if(isFail) actions.push(`<button onclick="act('${t.id}','resume')">↻ 重试</button>`);
  const name=t.name||t.fid||'?';
  const size=gb(t.size);
  const dl=gb(t.downloaded);
  const spd=mb(t.speed);
  const e=eta(t.eta||(t.size&&t.speed?(t.size-t.downloaded)/t.speed:-1));
  const err=t.error?'<div class="r" style="color:#ef4444">'+esc(t.error)+'</div>':'';
  return `<div class="card">
    <div class="h"><div class="n">${esc(name)}</div>${statusBadge(t.status)}</div>
    <div class="bar"><div class="${barClass}" style="width:${pct}%"></div></div>
    <div class="r"><span>${pct.toFixed(1)}%</span><span>${dl} / ${size}</span></div>
    ${isActive?`<div class="r"><span>${spd}/s</span><span>ETA ${e}</span><span>${t.done_chunks||0}/${t.nchunks||0} 块</span></div>`:''}
    ${err}
    ${actions.length?`<div class="act">${actions.join('')}</div>`:''}
  </div>`;
}

function render(){
  const filtered=_tasks.filter(t=>_filter==='all'||t.status===_filter);
  const el=document.getElementById('list');
  if(filtered.length===0){
    el.innerHTML='<div class="empty"><div class="big">📂</div>暂无任务</div>';
    return;
  }
  el.innerHTML=filtered.map(renderCard).join('');
  // 更新计数
  ['all','active','completed','failed'].forEach(f=>{
    const c=_tasks.filter(t=>f==='all'||t.status===f).length;
    document.getElementById('c_'+f).textContent=c;
  });
  document.getElementById('ftitle').textContent=document.querySelector('.f.act')?.textContent?.trim()||'全部';
}

function setF(el){
  document.querySelectorAll('.f').forEach(x=>x.classList.remove('act'));
  el.classList.add('act');
  _filter=el.dataset.f;
  render();
}

async function loadTasks(){
  try{
    const d=await(await fetch('/api/tasks')).json();
    _tasks=d.tasks||[];
    render();
  }catch(e){}
}

async function act(id,action){
  try{
    const d=await(await fetch(`/api/tasks/${id}/${action}`,{method:'POST'})).json();
    if(!d.ok) alert(d.error);
    loadTasks();
  }catch(e){}
}

async function rm(id){
  try{
    await fetch(`/api/tasks/${id}`,{method:'DELETE'});
    loadTasks();
  }catch(e){}
}

function showNew(){document.getElementById('modalNew').classList.add('show');document.getElementById('inpFid').focus();}
function showSettings(){
  document.getElementById('modalSet').classList.add('show');
  fetch('/api/settings').then(r=>r.json()).then(d=>{
    document.getElementById('inpOutdir').value=d.outdir||'';
    document.getElementById('inpCookie').placeholder=d.has_cookie?'已配置 (留空不变)':'夸克完整 Cookie';
    document.getElementById('setMsg').textContent='';
  });
}
function closeModal(id){document.getElementById(id).classList.remove('show');}

async function startNew(){
  const fid=document.getElementById('inpFid').value.trim();
  const msg=document.getElementById('newMsg');
  if(!fid){msg.textContent='❌ 请填写 fid';return;}
  msg.textContent='⏳ 创建中…';
  try{
    const d=await(await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fid})})).json();
    const allOk=d.results?.every(r=>r.ok);
    if(allOk){msg.textContent='✅ 已添加';document.getElementById('inpFid').value='';setTimeout(loadTasks,500);setTimeout(()=>closeModal('modalNew'),800);}
    else{
      const errs=d.results?.filter(r=>!r.ok).map(r=>r.fid+': '+r.error).join('; ');
      msg.textContent='❌ '+errs;
    }
  }catch(e){msg.textContent='❌ '+e;}
}

async function saveSettings(){
  const outdir=document.getElementById('inpOutdir').value.trim();
  const cookie=document.getElementById('inpCookie').value;
  const body={outdir};
  if(cookie.trim()) body.cookie=cookie.trim();
  try{
    const d=await(await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    const msg=document.getElementById('setMsg');
    if(d.ok){msg.textContent='✅ 已保存';msg.className='ok';document.getElementById('inpCookie').value='';}
    else{msg.textContent='❌ 保存失败';msg.className='err';}
    setTimeout(loadTasks,500);
  }catch(e){}
}

// 点击遮罩关闭弹窗
document.querySelectorAll('.modal').forEach(m=>{m.addEventListener('click',e=>{if(e.target===m)m.classList.remove('show');})});

// 键盘快捷键
document.addEventListener('keydown',e=>{
  if(e.key==='Escape') document.querySelectorAll('.modal.show').forEach(m=>m.classList.remove('show'));
});

// 设置目录显示
document.getElementById('fdir').textContent='监控: '+(document.getElementById('inpOutdir')?.value||'~');

// 初始加载 + 定时刷新
loadTasks();
setInterval(loadTasks,2000);
</script></body></html>"""

# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    print(f"夸克下载管理器  http://localhost:{PORT}")
    print(f"配置文件: {CONFIG_PATH}")
    print(f"任务数据: {TASKS_PATH}")
    print("Ctrl+C 退出")
    server = ThreadingServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出。任务数据已保存。")
        server.server_close()