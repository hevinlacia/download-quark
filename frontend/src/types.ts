export interface Task {
  id: string;
  engine: "aria2" | "quark";
  type: "url" | "magnet" | "torrent" | "quark";
  name: string;
  size: number;
  downloaded: number;
  speed: number;
  pct: number;
  status: "active" | "waiting" | "paused" | "completed" | "failed" | "cancelled";
  error: string | null;
  created_at: number;
  completed_at: number | null;
}

export interface Settings {
  outdir: string;
  has_cookie: boolean;
  aria2_running: boolean;
}

export type FilterKey = "all" | "active" | "completed" | "failed";
