"""aria2 守护进程管理 + JSON-RPC 客户端。"""
import json
import os
import subprocess
import time
import urllib.request

RPC_PORT = 6800
RPC_SECRET = "downloader"  # aria2 RPC token
ARIA2_CONF_DIR = os.path.expanduser("~/.config/downloader/aria2")
ARIA2_SESSION = os.path.join(ARIA2_CONF_DIR, "session")
ARIA2_CONF = os.path.join(ARIA2_CONF_DIR, "aria2.conf")


def ensure_conf():
    """确保 aria2 配置目录和配置文件存在。"""
    os.makedirs(ARIA2_CONF_DIR, exist_ok=True)
    if not os.path.exists(ARIA2_CONF):
        with open(ARIA2_CONF, "w") as f:
            f.write(f"""# aria2 config for downloader
enable-rpc=true
rpc-listen-all=true
rpc-listen-port={RPC_PORT}
rpc-secret={RPC_SECRET}
rpc-allow-origin-all=true
continue=true
max-concurrent-downloads=10
max-connection-per-server=16
split=16
min-split-size=1M
dir={os.path.expanduser("~/下载")}
disk-cache=64M
file-allocation=falloc
session={ARIA2_SESSION}
save-session-interval=30
auto-file-renaming=false
allow-overwrite=true
bt-metadata-only=false
bt-save-metadata=true
seed-time=0
""")
    # 创建空 session 文件
    if not os.path.exists(ARIA2_SESSION):
        open(ARIA2_SESSION, "w").close()


_proc = None


def start():
    """启动 aria2c 守护进程。"""
    global _proc
    if _proc and _proc.poll() is None:
        return
    ensure_conf()
    _proc = subprocess.Popen(
        ["aria2c", "--conf-path=" + ARIA2_CONF, "--summary-interval=0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    time.sleep(0.5)
    return _proc


def stop():
    """停止 aria2c。"""
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        _proc.wait(timeout=5)
    _proc = None


def is_running():
    """检查 aria2 是否在运行 (优先检查 RPC 是否响应)。"""
    if _proc and _proc.poll() is None:
        return True
    # 尝试 RPC 调用，能连通说明有 aria2 在跑 (可能是其他进程启动的)
    try:
        _rpc("aria2.getVersion")
        return True
    except Exception:
        return False


# ============================================================
# JSON-RPC 客户端
# ============================================================
_id = 0


def _rpc(method, params=None):
    """调用 aria2 JSON-RPC，返回 result 或 raise。"""
    global _id
    _id += 1
    body = json.dumps({
        "jsonrpc": "2.0", "id": _id,
        "method": method,
        "params": ["token:" + RPC_SECRET] + (params or []),
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:{RPC_PORT}/jsonrpc",
        data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        j = json.load(r)
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "aria2 error"))
    return j.get("result")


def add_uri(uri, outdir=None, filename=None):
    """添加 URL/magnet 下载，返回 gid。"""
    opts = {}
    if outdir:
        opts["dir"] = outdir
    if filename:
        opts["out"] = filename
    return _rpc("aria2.addUri", [[uri], opts])


def add_torrent(torrent_path, outdir=None):
    """添加 .torrent 文件，返回 gid。"""
    import base64
    with open(torrent_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    opts = {}
    if outdir:
        opts["dir"] = outdir
    return _rpc("aria2.addTorrent", [b64, [], opts])


def tell_status(gid):
    """查询任务状态，返回 dict。"""
    keys = ["gid", "status", "totalLength", "completedLength",
            "downloadSpeed", "uploadSpeed", "files", "errorCode", "errorMessage"]
    return _rpc("aria2.tellStatus", [gid, keys])


def pause(gid):
    return _rpc("aria2.pause", [gid])


def resume(gid):
    return _rpc("aria2.unpause", [gid])


def cancel(gid):
    """删除任务（含文件）。"""
    try:
        _rpc("aria2.removeDownloadResult", [gid])
    except Exception:
        pass
    return _rpc("aria2.forceRemove", [gid])


def remove(gid):
    """删除任务记录。"""
    _rpc("aria2.pause", [gid])
    try:
        _rpc("aria2.removeDownloadResult", [gid])
    except Exception:
        pass
    return _rpc("aria2.forceRemove", [gid])


def tell_active():
    """所有活动任务。"""
    keys = ["gid", "status", "totalLength", "completedLength",
            "downloadSpeed", "files", "errorCode", "errorMessage"]
    return _rpc("aria2.tellActive", [keys])


def tell_waiting():
    keys = ["gid", "status", "totalLength", "completedLength",
            "downloadSpeed", "files", "errorCode", "errorMessage"]
    return _rpc("aria2.tellWaiting", [0, 100, keys])


def tell_stopped():
    keys = ["gid", "status", "totalLength", "completedLength",
            "downloadSpeed", "files", "errorCode", "errorMessage"]
    return _rpc("aria2.tellStopped", [0, 100, keys])


def all_tasks():
    """返回所有 aria2 任务的原始数据列表。"""
    try:
        return (tell_active() or []) + (tell_waiting() or []) + (tell_stopped() or [])
    except Exception:
        return []
