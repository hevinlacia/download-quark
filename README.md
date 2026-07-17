# download-quark

夸克网盘大文件直链下载工具，绕过网页端强制跳客户端的限制，附带 web 监控仪表盘。

## 为什么需要这个

夸克网页端 (`pan.quark.cn`) 下载大文件时会返回 `23018 download file size limit`，强制跳转 PC 客户端。本工具用 PC 客户端 UA + `drive.quark.cn` 接口绕过该限制，直接取 OSS 直链下载，无需安装客户端。

## 原理

1. 接口域名 `drive-pc.quark.cn` → `drive.quark.cn`
2. User-Agent 伪装成夸克 PC 客户端 `quark-cloud-drive/2.5.20`
3. POST `{"fids":["<fid>"]}` 取直链
4. **不用 aria2**（夸克会把它限速到 ~1.5MB/s），改用 urllib 16 并发 × 100MB 小分块，实测 30-55MB/s

## 用法

### 1. 取 Cookie 和 fid

在夸克网盘网页打开文件列表页，浏览器 DevTools 复制任意请求的 `Cookie:` 头；用文件列表接口（`drive-pc.quark.cn/1/clouddrive/file/sort`）的响应 `data.list[].fid` 拿到文件 fid。

```bash
# 列出某目录下的文件 fid
curl -s '<sort接口URL>' -H 'Cookie: <你的Cookie>' \
  | python3 -c "import sys,json;[print(f['fid'],f['file_name'],f['size']) for f in json.load(sys.stdin)['data']['list']]"
```

### 2. 下载

```bash
export QUARK_COOKIE='<完整Cookie>'
cd <存放目录>
python3 quark_dl.py <fid1> [<fid2> ...]
```

可选环境变量：`CHUNK_MB`（默认 100）、`CONC`（默认 16）、`OUTDIR`（默认当前目录）。

特性：16 路并行分块、断点续传（中断重跑同命令即续传）、每块自动重试 10 次（治 SSL 断连）、实时进度条。

### 3. Web 监控（可选）

```bash
# 终端1: 启动监控（常驻）
python3 quark_monitor.py <下载目录> [端口]
```

浏览器打开 `http://localhost:7788`，实时查看所有下载的进度条、速度、ETA。监控进程与下载进程解耦，互不影响。

### 4. 后台下载 + 监控（推荐）

```bash
export QUARK_COOKIE='<完整Cookie>'
DLDIR=~/下载/网盘

# 启动监控（后台常驻）
nohup python3 quark_monitor.py "$DLDIR" 7788 > /tmp/quark_monitor.log 2>&1 & disown

# 后台启动下载（不阻塞）
nohup python3 quark_dl.py <fid> > "$DLDIR/dl.log" 2>&1 & disown

# 随时浏览器查看 http://localhost:7788
```

## 文件

- `quark_dl.py` — 下载器。写 `.X.parts/.meta.json` 供监控读取，完成后写 `.quark_history.jsonl`。
- `quark_monitor.py` — web 监控仪表盘，扫描下载目录渲染实时进度。

## 注意

- 直链有效期约 5-9 小时，脚本每次运行重新取直链，单次下载（<15 分钟）不会过期。
- Cookie 不硬编码，走 `QUARK_COOKIE` 环境变量。
- fid 是**文件**的 fid，不是目录的 `pdir_fid`。
