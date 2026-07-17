# download-quark

夸克网盘大文件直链下载工具，绕过网页端强制跳客户端的限制，附带 web 控制面板（配置下载目录、网页启动下载、实时监控进度）。

## 为什么需要这个

夸克网页端 (`pan.quark.cn`) 下载大文件时返回 `23018 download file size limit`，强制跳转 PC 客户端。本工具用 PC 客户端 UA + `drive.quark.cn` 接口绕过该限制，直接取 OSS 直链下载，无需安装客户端。

## 原理

1. 接口域名 `drive-pc.quark.cn` -> `drive.quark.cn`
2. User-Agent 伪装成夸克 PC 客户端 `quark-cloud-drive/2.5.20`
3. POST `{"fids":["<fid>"]}` 取直链
4. **不用 aria2**（夸克会把它限速到 ~1.5MB/s），改用 urllib 16 并发 × 100MB 小分块，实测 30-55MB/s

## 快速开始（推荐：web 控制面板）

```bash
# 启动面板（常驻）
python3 quark_monitor.py ~/下载/网盘 7788
```

浏览器打开 `http://localhost:7788`：

- **设置**：填下载目录 + 夸克 Cookie，保存（存到 `~/.config/download-quark/config.json`，Cookie 不回传前端）
- **新建下载**：粘贴 fid（多个用空格/换行分隔），点「开始下载」即后台启动，不阻塞面板
- **进行中**：实时进度条 / 速度 / ETA / 完成块数
- **历史**：已完成的下载记录

面板与下载进程解耦：下载在独立后台进程跑（`start_new_session` 挂载，面板重启不影响进行中的下载），面板只扫描文件系统显示进度。

## 取 Cookie 和 fid

- **Cookie**：夸克网盘网页打开文件列表页，浏览器 DevTools 复制任意请求的 `Cookie:` 头。
- **fid**：用文件列表接口响应的 `data.list[].fid`（注意是文件的 fid，不是目录的 `pdir_fid`）。

```bash
curl -s '<sort接口URL>' -H 'Cookie: <你的Cookie>' \
  | python3 -c "import sys,json;[print(f['fid'],f['file_name'],f['size']) for f in json.load(sys.stdin)['data']['list']]"
```

## 命令行方式（可选）

CLI 与 web 面板共用同一份配置（`~/.config/download-quark/config.json`），Cookie/目录设一次两边通用。

```bash
# 方式一：用 web 设好的配置直接下
python3 quark_dl.py <fid1> [<fid2> ...]

# 方式二：临时用环境变量覆盖
QUARK_COOKIE='<Cookie>' OUTDIR=~/下载/网盘 python3 quark_dl.py <fid>

# 后台运行面板（开机即用）
nohup python3 quark_monitor.py ~/下载/网盘 7788 > /tmp/quark_monitor.log 2>&1 & disown
```

特性：16 路并行分块、断点续传（中断重跑同命令即续传）、每块自动重试 10 次（治 SSL 断连）、实时进度条。

可选环境变量：`CHUNK_MB`（默认 100）、`CONC`（默认 16）、`OUTDIR`、`QUARK_COOKIE`。

## 文件

- `quark_dl.py` - 下载器。读配置/env，写 `.X.parts/.meta.json` 供监控读取，完成后写 `.quark_history.jsonl`。
- `quark_monitor.py` - web 控制面板。监控 + 配置 + 启动下载。

## 注意

- 直链有效期约 5-9 小时，脚本每次运行重新取直链，单次下载（<15 分钟）不会过期。
- Cookie 存本地配置文件，仅在 localhost 传输；`GET /config` 不回传 Cookie 内容（只返回 `has_cookie` 标记）。
- fid 是**文件**的 fid，不是目录的 `pdir_fid`。
- 监听 `0.0.0.0`，同局域网手机可访问 `http://<电脑IP>:7788`。
