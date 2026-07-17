"""downloader 后端 -- 统一下载管理 API (FastAPI)

管理两类下载引擎:
- aria2: HTTP/FTP/BT/磁力链 (通过 JSON-RPC)
- quark: 夸克网盘大文件 (通过 engine.py)
"""
import os
import sys
import json
import time
import uuid
import threading
import tempfile
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# 确保能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aria2c
from engine import download_task

CONFIG_DIR = os.path.expanduser("~/.config/downloader")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
TASKS_PATH = os.path.join(CONFIG_DIR, "tasks.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

# ============================================================
# 配置
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

# ============================================================
# Quark 任务管理 (引擎内部状态)
# ============================================================
_QUARK_TASKS = {}  # gid -> task dict
_QUARK_LOCK = threading.Lock()
_QUARK_WORKERS = {}  # gid -> {stop_event, thread}

def load_quark_tasks():
    global _QUARK_TASKS
    try:
        with open(TASKS_PATH) as f:
            data = json.load(f)
        # 兼容旧版列表格式: 转成空字典重新开始
        _QUARK_TASKS = data if isinstance(data, dict) else {}
    except Exception:
        _QUARK_TASKS = {}

def save_quark_tasks():
    with open(TASKS_PATH, "w") as f:
        json.dump(_QUARK_TASKS, f, ensure_ascii=False, indent=2)

load_quark_tasks()

def _run_quark_worker(task):
    gid = task["id"]
    cfg = load_config()
    cookie = cfg.get("cookie", "")
    outdir = task.get("outdir") or cfg.get("outdir") or os.path.expanduser("~/下载")

    def progress_cb(downloaded, total, speed, pct, done, nchunks):
        with _QUARK_LOCK:
            task["downloaded"] = downloaded
            task["size"] = total
            task["speed"] = speed
            task["pct"] = round(pct, 1)
            task["done_chunks"] = done
            task["nchunks"] = nchunks

    w = _QUARK_WORKERS.get(gid)
    stop_event = w["stop_event"] if w else threading.Event()

    try:
        ok, name, err = download_task(task["fid"], outdir=outdir, cookie=cookie,
                                       progress_cb=progress_cb, stop_event=stop_event)
        with _QUARK_LOCK:
            if stop_event.is_set():
                task["status"] = "paused"
            elif ok:
                task["status"] = "completed"
                task["pct"] = 100
                task["downloaded"] = task["size"]
                task["completed_at"] = time.time()
            else:
                task["status"] = "failed"
                task["error"] = err
    except Exception as e:
        with _QUARK_LOCK:
            task["status"] = "failed"
            task["error"] = str(e)
    finally:
        with _QUARK_LOCK:
            save_quark_tasks()
        _QUARK_WORKERS.pop(gid, None)


def quark_add(fid, outdir=None):
    gid = uuid.uuid4().hex[:16]
    cfg = load_config()
    if not cfg.get("cookie"):
        return None, "未配置夸克 Cookie"
    od = outdir or cfg.get("outdir") or os.path.expanduser("~/下载")
    task = {
        "id": gid, "engine": "quark", "type": "quark",
        "fid": fid.strip(), "name": fid.strip()[:12] + "...",
        "size": 0, "downloaded": 0, "speed": 0, "pct": 0,
        "status": "active", "error": None,
        "created_at": time.time(), "completed_at": None,
        "outdir": od, "nchunks": 0, "done_chunks": 0,
    }
    with _QUARK_LOCK:
        _QUARK_TASKS[gid] = task
        save_quark_tasks()
    stop_event = threading.Event()
    _QUARK_WORKERS[gid] = {"stop_event": stop_event}
    t = threading.Thread(target=_run_quark_worker, args=(task,), daemon=True)
    t.start()
    return gid, None


def quark_pause(gid):
    with _QUARK_LOCK:
        t = _QUARK_TASKS.get(gid)
        if not t or t["status"] != "active":
            return False, "只能暂停进行中的任务"
        t["status"] = "paused"
        save_quark_tasks()
    w = _QUARK_WORKERS.get(gid)
    if w:
        w["stop_event"].set()
    return True, None


def quark_resume(gid):
    with _QUARK_LOCK:
        t = _QUARK_TASKS.get(gid)
        if not t or t["status"] not in ("paused", "failed"):
            return False, "只能恢复暂停/失败的任务"
        t["status"] = "active"
        t["error"] = None
        save_quark_tasks()
    stop_event = threading.Event()
    _QUARK_WORKERS[gid] = {"stop_event": stop_event}
    t2 = threading.Thread(target=_run_quark_worker, args=(t,), daemon=True)
    t2.start()
    return True, None


def quark_cancel(gid):
    with _QUARK_LOCK:
        t = _QUARK_TASKS.get(gid)
        if not t:
            return False, "任务不存在"
        t["status"] = "cancelled"
        save_quark_tasks()
    w = _QUARK_WORKERS.get(gid)
    if w:
        w["stop_event"].set()
    return True, None


def quark_remove(gid):
    quark_cancel(gid)
    with _QUARK_LOCK:
        _QUARK_TASKS.pop(gid, None)
        save_quark_tasks()
    return True, None


# ============================================================
# 统一任务模型
# ============================================================
def _aria2_to_task(raw):
    """把 aria2 原始状态转成统一 task。"""
    gid = raw.get("gid", "")
    total = int(raw.get("totalLength", 0))
    done = int(raw.get("completedLength", 0))
    speed = int(raw.get("downloadSpeed", 0))
    status = raw.get("status", "")
    # 状态映射
    smap = {"active": "active", "waiting": "waiting", "paused": "paused",
            "complete": "completed", "removed": "cancelled",
            "error": "failed", "complete": "completed"}
    ust = smap.get(status, status)
    # 文件名
    name = "?"
    files = raw.get("files", [])
    if files:
        path = files[0].get("path", "")
        if path:
            name = os.path.basename(path)
        elif files[0].get("uris"):
            u = files[0]["uris"][0].get("uri", "")
            name = u.split("/")[-1][:60] or u[:40]
    pct = round(done / total * 100, 1) if total else 0
    # 类型推断
    engine = "aria2"
    dtype = "url"
    if files and files[0].get("uris"):
        u = files[0]["uris"][0].get("uri", "")
        if u.startswith("magnet:"):
            dtype = "magnet"
    elif files and len(files) > 1:
        dtype = "torrent"
    return {
        "id": gid, "engine": engine, "type": dtype,
        "name": name, "size": total, "downloaded": done,
        "speed": speed, "pct": pct, "status": ust,
        "error": raw.get("errorMessage") if ust == "failed" else None,
        "created_at": 0, "completed_at": None,
    }


def all_tasks():
    """返回所有任务 (aria2 + quark) 的统一列表。"""
    tasks = []
    # aria2
    try:
        for raw in aria2c.all_tasks():
            tasks.append(_aria2_to_task(raw))
    except Exception:
        pass
    # quark
    with _QUARK_LOCK:
        for t in _QUARK_TASKS.values():
            tasks.append(dict(t))
    # 排序: active > waiting > paused > completed/failed/cancelled, 再按 created_at
    order = {"active": 0, "waiting": 1, "paused": 2, "completed": 3, "failed": 4, "cancelled": 5}
    tasks.sort(key=lambda x: (order.get(x["status"], 9), -(x.get("created_at") or 0)))
    return tasks


# ============================================================
# FastAPI
# ============================================================
app = FastAPI(title="downloader")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


class TaskCreate(BaseModel):
    type: str  # url, magnet, torrent, quark
    uri: Optional[str] = None  # for url/magnet
    fid: Optional[str] = None  # for quark
    outdir: Optional[str] = None


class SettingsUpdate(BaseModel):
    outdir: Optional[str] = None
    cookie: Optional[str] = None


@app.on_event("startup")
def _startup():
    aria2c.start()
    # 恢复 quark active -> paused
    with _QUARK_LOCK:
        for t in _QUARK_TASKS.values():
            if t["status"] == "active":
                t["status"] = "paused"
        save_quark_tasks()


@app.on_event("shutdown")
def _shutdown():
    aria2c.stop()


@app.get("/api/tasks")
def get_tasks():
    return {"tasks": all_tasks()}


@app.post("/api/tasks")
def create_task(req: TaskCreate):
    cfg = load_config()
    outdir = req.outdir or cfg.get("outdir") or os.path.expanduser("~/下载")
    if req.type in ("url", "magnet"):
        if not req.uri:
            return JSONResponse({"error": "缺少 uri"}, 400)
        try:
            gid = aria2c.add_uri(req.uri, outdir=outdir)
            return {"ok": True, "id": gid, "engine": "aria2"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)
    elif req.type == "torrent":
        return JSONResponse({"error": "torrent 需要上传文件，用 /api/tasks/torrent"}, 400)
    elif req.type == "quark":
        if not req.fid:
            return JSONResponse({"error": "缺少 fid"}, 400)
        gid, err = quark_add(req.fid, outdir)
        if err:
            return JSONResponse({"error": err}, 400)
        return {"ok": True, "id": gid, "engine": "quark"}
    return JSONResponse({"error": f"未知类型: {req.type}"}, 400)


@app.post("/api/tasks/torrent")
async def create_torrent(request: Request):
    """上传 .torrent 文件创建任务。"""
    cfg = load_config()
    outdir = cfg.get("outdir") or os.path.expanduser("~/下载")
    body = await request.body()
    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
        f.write(body)
        tmp = f.name
    try:
        gid = aria2c.add_torrent(tmp, outdir=outdir)
        return {"ok": True, "id": gid, "engine": "aria2"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)
    finally:
        os.unlink(tmp)


@app.post("/api/tasks/{tid}/{action}")
def task_action(tid: str, action: str):
    # 先查 quark
    with _QUARK_LOCK:
        is_quark = tid in _QUARK_TASKS
    if is_quark:
        fn = {"pause": quark_pause, "resume": quark_resume, "cancel": quark_cancel}.get(action)
        if fn:
            ok, err = fn(tid)
            return {"ok": ok, "error": err}
    else:
        # aria2
        try:
            if action == "pause":
                aria2c.pause(tid)
            elif action == "resume":
                aria2c.resume(tid)
            elif action == "cancel":
                aria2c.cancel(tid)
            else:
                return JSONResponse({"error": f"未知操作: {action}"}, 400)
            return {"ok": True}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)


@app.delete("/api/tasks/{tid}")
def delete_task(tid: str):
    with _QUARK_LOCK:
        is_quark = tid in _QUARK_TASKS
    if is_quark:
        ok, err = quark_remove(tid)
        return {"ok": ok, "error": err}
    try:
        aria2c.remove(tid)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


@app.get("/api/settings")
def get_settings():
    cfg = load_config()
    return {"outdir": cfg.get("outdir", ""), "has_cookie": bool(cfg.get("cookie")),
            "aria2_running": aria2c.is_running()}


@app.post("/api/settings")
def update_settings(req: SettingsUpdate):
    cfg = load_config()
    if req.outdir is not None:
        cfg["outdir"] = req.outdir.strip()
    if req.cookie and req.cookie.strip():
        cfg["cookie"] = req.cookie.strip()
    save_config(cfg)
    return {"ok": True, "outdir": cfg.get("outdir", "")}


@app.get("/api/aria2/restart")
def restart_aria2():
    aria2c.stop()
    aria2c.start()
    return {"ok": True, "running": aria2c.is_running()}


# 静态文件: 前端构建产物
if os.path.isdir(FRONTEND_DIST):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{path:path}")
    def static(path: str):
        f = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
