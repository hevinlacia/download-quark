# Downloader

通用下载管理器，Motrix 风格 web UI，支持 HTTP/FTP/磁力链/种子（aria2）+ 夸克网盘（自研引擎绕过大文件限制）。

## 架构

```
backend/   Python (FastAPI + uvicorn)
           ├── server.py    统一任务 API + 静态文件服务
           ├── aria2c.py    aria2 守护进程管理 + JSON-RPC
           └── engine.py    夸克网盘下载引擎
frontend/  React + Vite + TypeScript + Tailwind CSS
           构建产物 dist/ 由后端 serve
```

## 安装

```bash
# 后端
cd backend && uv venv && uv pip install fastapi uvicorn

# 前端
cd frontend && bun install && bun run build
```

## 运行

```bash
cd backend
uv run uvicorn server:app --host 0.0.0.0 --port 7788
```

浏览器打开 `http://localhost:7788`

## systemd 服务

```bash
# 服务文件: ~/.config/systemd/user/downloader.service
systemctl --user enable --now downloader
```

## 功能

- **URL/磁力链下载** (aria2 引擎)
- **种子文件下载** (aria2 BT)
- **夸克网盘下载** (自研引擎，绕过大文件限制，多线程分块)
- 任务管理：暂停/恢复/取消/删除/重试
- 实时进度：进度条/速度/ETA/块数
- 配置持久化：下载目录 + 夸克 Cookie
- 暗色主题 web UI
- aria2 守护进程自动管理
- 开机自启 (systemd)
