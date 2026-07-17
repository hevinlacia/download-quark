export function fmtBytes(b: number): string {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = b;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
}

export function fmtSpeed(b: number): string {
  return fmtBytes(b) + "/s";
}

export function fmtETA(s: number): string {
  if (s < 0 || s > 999999) return "--";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  if (m < 60) return `${m}m${String(r).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h${String(m % 60).padStart(2, "0")}m`;
}

export const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  waiting: "等待中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const STATUS_COLOR: Record<string, string> = {
  active: "bg-blue-500/20 text-blue-400",
  waiting: "bg-yellow-500/20 text-yellow-400",
  paused: "bg-gray-500/20 text-gray-400",
  completed: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
  cancelled: "bg-gray-500/20 text-gray-500",
};

export const ENGINE_LABEL: Record<string, string> = {
  aria2: "Aria2",
  quark: "夸克",
};

export const TYPE_ICON: Record<string, string> = {
  url: "🔗",
  magnet: "🧲",
  torrent: "🌊",
  quark: "☁️",
};
