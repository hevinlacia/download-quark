import type { Task, Settings } from "./types";

const BASE = "/api";

async function json<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  return r.json();
}

export async function getTasks(): Promise<Task[]> {
  const d = await json<{ tasks: Task[] }>(`${BASE}/tasks`);
  return d.tasks;
}

export async function createTask(body: {
  type: string;
  uri?: string;
  fid?: string;
  outdir?: string;
}): Promise<{ ok: boolean; id?: string; error?: string }> {
  return json(`${BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function createTorrent(file: File): Promise<{ ok: boolean; id?: string; error?: string }> {
  const buf = await file.arrayBuffer();
  const r = await fetch(`${BASE}/tasks/torrent`, {
    method: "POST",
    headers: { "Content-Type": "application/x-bittorrent" },
    body: buf,
  });
  return r.json();
}

export async function taskAction(id: string, action: string): Promise<{ ok: boolean; error?: string }> {
  return json(`${BASE}/tasks/${id}/${action}`, { method: "POST" });
}

export async function deleteTask(id: string): Promise<{ ok: boolean; error?: string }> {
  return json(`${BASE}/tasks/${id}`, { method: "DELETE" });
}

export async function getSettings(): Promise<Settings> {
  return json(`${BASE}/settings`);
}

export async function saveSettings(body: { outdir?: string; cookie?: string }): Promise<{ ok: boolean; outdir?: string; error?: string }> {
  return json(`${BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
