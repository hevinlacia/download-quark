#!/usr/bin/env python3
# quark_dl.py -- 夸克网盘直链下载器
# 并行分块 + 断点续传 + 自动重试 + 写 .meta.json 供 web 监控读取
#
# 用法:
#   export QUARK_COOKIE='<从浏览器复制的完整 Cookie>'
#   python3 quark_dl.py <fid> [<fid> ...]
#
# 可选环境变量: CHUNK_MB(默认100) CONC(默认16) OUTDIR(默认当前目录)
import json, os, sys, time, shutil, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

COOKIE = os.environ.get("QUARK_COOKIE", "").strip()
QUARK_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) quark-cloud-drive/2.5.20 "
            "Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 Safari/537.36 "
            "Channel/pckk_other_ch")
CHUNK_MB = int(os.environ.get("CHUNK_MB", "100"))
CONC = int(os.environ.get("CONC", "16"))
OUTDIR = os.environ.get("OUTDIR") or os.getcwd()


def die(msg):
    print(f"❌ {msg}", file=sys.stderr); sys.exit(1)


def get_url_info(fid):
    """用 PC 客户端 UA 调 drive.quark.cn 取直链+文件名+大小(绕过大文件限制)。"""
    data = json.dumps({"fids": [fid]}).encode()
    req = urllib.request.Request(
        "https://drive.quark.cn/1/clouddrive/file/download?pr=ucpro&fr=pc",
        data=data, method="POST",
        headers={"User-Agent": QUARK_UA, "Content-Type": "application/json", "Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    if j.get("code") != 0:
        die(f"取直链失败 fid={fid}: {j.get('code')} {j.get('message')}")
    d = j["data"][0]
    return d["download_url"], d["file_name"], int(d["size"])


def download_chunk(url, partpath, start, end):
    expected = end - start + 1
    last_err = None
    for _ in range(10):
        have = os.path.getsize(partpath) if os.path.exists(partpath) else 0
        if have > expected:
            os.remove(partpath); have = 0
        if have == expected:
            return expected
        rs = start + have
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": QUARK_UA, "Cookie": COOKIE, "Range": f"bytes={rs}-{end}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                mode = "wb" if (have > 0 and r.status != 206) else ("ab" if have > 0 else "wb")
                with open(partpath, mode) as f:
                    while True:
                        buf = r.read(1048576)
                        if not buf:
                            break
                        f.write(buf)
            return expected
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise last_err


def fmt(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}PB"


def fmt_eta(s):
    if s < 0 or s > 99999:
        return "--"
    if s < 60:
        return f"{s:.0f}s"
    m, s = divmod(int(s), 60)
    return f"{m}m{s:02d}s" if m < 60 else f"{m//60}h{m%60:02d}m"


def bar(pct, w=20):
    f = int(w * pct / 100)
    return "[" + "█" * f + "░" * (w - f) + "]"


def cur_bytes(partdir, n):
    t = 0
    for j in range(n):
        try:
            t += os.path.getsize(os.path.join(partdir, f"p_{j:05d}"))
        except OSError:
            pass
    return t


def log_history(name, size, ok, final, dt):
    try:
        with open(os.path.join(OUTDIR, ".quark_history.jsonl"), "a") as hf:
            json.dump({"name": name, "size": size, "ok": ok,
                       "avg_speed": final / dt if dt > 0 else 0, "duration": dt,
                       "finished_at": time.time()}, hf)
            hf.write("\n")
    except Exception:
        pass


def download_one(fid):
    url, name, size = get_url_info(fid)
    out = os.path.join(OUTDIR, name)
    print(f">>> {name}  {fmt(size)}  ({CHUNK_MB}MB块 ×{CONC}并发)")
    if os.path.exists(out) and os.path.getsize(out) == size:
        print("    已存在且完整，跳过"); return True

    partdir = os.path.join(OUTDIR, "." + name + ".parts")
    os.makedirs(partdir, exist_ok=True)
    chunk = CHUNK_MB * 1024 * 1024
    nchunks = (size + chunk - 1) // chunk
    jobs = [(i, i * chunk, min(i * chunk + chunk - 1, size - 1)) for i in range(nchunks)]

    # 写元信息供 web 监控读取
    t0 = time.time()
    try:
        with open(os.path.join(partdir, ".meta.json"), "w") as mf:
            json.dump({"name": name, "size": size, "nchunks": nchunks,
                       "chunk_mb": CHUNK_MB, "started": t0}, mf)
    except Exception:
        pass

    stop = threading.Event()
    done = [0]

    def monitor():
        last, lt = cur_bytes(partdir, nchunks), time.time()
        while not stop.is_set():
            stop.wait(1)
            c = cur_bytes(partdir, nchunks); now = time.time(); dt = now - lt
            inst = (c - last) / dt if dt > 0 else 0
            avg = c / (now - t0) if now > t0 else 0
            last, lt = c, now
            pct = c / size * 100
            eta = (size - c) / inst if inst > 0 else -1
            print(f"\r    {bar(pct)} {pct:4.1f}% {c/1073741824:.1f}/{size/1073741824:.1f}G "
                  f"{fmt(inst)}/s 均{fmt(avg)}/s ETA {fmt_eta(eta)} {done[0]}/{nchunks}",
                  end="", flush=True)

    mon = threading.Thread(target=monitor, daemon=True); mon.start()
    with ThreadPoolExecutor(max_workers=CONC) as ex:
        futs = {ex.submit(download_chunk, url, os.path.join(partdir, f"p_{i:05d}"), s, e): i
                for i, s, e in jobs}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                stop.set(); mon.join()
                print(f"\n    ❌ 块{futs[fut]}重试10次仍失败: {e}")
                print(f"    直链可能已过期(5-9h有效)，重跑本脚本会续传")
                return False
            done[0] += 1
    stop.set(); mon.join(); print()

    for i, s, e in jobs:
        if os.path.getsize(os.path.join(partdir, f"p_{i:05d}")) != (e - s + 1):
            print(f"    ❌ 块{i}不完整，重跑续传即可"); return False
    print("    合并...")
    with open(out, "wb") as out_f:
        for i in range(nchunks):
            with open(os.path.join(partdir, f"p_{i:05d}"), "rb") as pf:
                shutil.copyfileobj(pf, out_f, 1048576)
    shutil.rmtree(partdir)
    final, dt = os.path.getsize(out), time.time() - t0
    ok = final == size
    print(f"    {'✅' if ok else '❌'} {fmt(final)}  均速 {fmt(final/dt)}/s  耗时 {fmt_eta(dt)}")
    log_history(name, size, ok, final, dt)
    return ok


def main():
    if not COOKIE:
        die("未设置 QUARK_COOKIE 环境变量。在夸克网盘网页复制请求的 Cookie 头后: "
            "export QUARK_COOKIE='...'")
    fids = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not fids:
        die("用法: QUARK_COOKIE='...' python3 quark_dl.py <fid> [<fid> ...]")
    os.makedirs(OUTDIR, exist_ok=True)
    rc = 0
    for fid in fids:
        if not download_one(fid):
            rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
