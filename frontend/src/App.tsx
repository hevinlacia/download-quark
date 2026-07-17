import { useState, useEffect, useCallback } from "react";
import type { Task, FilterKey } from "./types";
import { getTasks, getSettings } from "./api";
import { TaskCard } from "./components/TaskCard";
import { AddTaskDialog } from "./components/AddTaskDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { STATUS_LABEL } from "./utils";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "active", label: "进行中" },
  { key: "completed", label: "已完成" },
  { key: "failed", label: "失败" },
];

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [showAdd, setShowAdd] = useState(false);
  const [showSet, setShowSet] = useState(false);
  const [aria2On, setAria2On] = useState(false);
  const [outdir, setOutdir] = useState("");

  const reload = useCallback(() => {
    getTasks().then(setTasks).catch(() => {});
  }, []);

  useEffect(() => {
    reload();
    getSettings().then((d) => { setAria2On(d.aria2_running); setOutdir(d.outdir || ""); });
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [reload]);

  const filtered = tasks.filter((t) => filter === "all" || t.status === filter || (filter === "active" && t.status === "waiting"));
  const counts = {
    all: tasks.length,
    active: tasks.filter((t) => t.status === "active" || t.status === "waiting").length,
    completed: tasks.filter((t) => t.status === "completed").length,
    failed: tasks.filter((t) => t.status === "failed").length,
  };

  return (
    <div className="flex h-screen bg-[#0f1115] text-gray-200 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[180px] bg-[#13161c] border-r border-[#1f232b] flex flex-col shrink-0">
        <div className="px-5 py-5">
          <h1 className="text-sm font-semibold text-gray-100">⬇️ Downloader</h1>
          <p className="text-[11px] text-gray-600 mt-1">通用下载管理器</p>
        </div>
        <nav className="flex-1 px-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors ${
                filter === f.key ? "bg-[#1a1d24] text-gray-100" : "text-gray-500 hover:text-gray-300 hover:bg-[#1a1d24]/50"
              }`}
            >
              <span>{f.label}</span>
              <span className="text-gray-600">{counts[f.key]}</span>
            </button>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-[#1f232b] space-y-1">
          <div className="flex items-center gap-1.5 text-[11px]">
            <span className={`w-1.5 h-1.5 rounded-full ${aria2On ? "bg-green-500" : "bg-red-500"}`} />
            <span className="text-gray-600">Aria2 {aria2On ? "运行中" : "未运行"}</span>
          </div>
          <div className="text-[10px] text-gray-700 truncate" title={outdir}>{outdir || "未设置目录"}</div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="flex items-center gap-3 px-5 py-3 border-b border-[#1f232b] shrink-0">
          <span className="text-sm text-gray-500 flex-1">
            {FILTERS.find((f) => f.key === filter)?.label} ({filtered.length})
          </span>
          <button onClick={reload} className="p-2 text-gray-500 hover:text-gray-300 rounded-lg hover:bg-[#1a1d24] transition-colors" title="刷新">
            🔄
          </button>
          <button onClick={() => setShowSet(true)} className="p-2 text-gray-500 hover:text-gray-300 rounded-lg hover:bg-[#1a1d24] transition-colors" title="设置">
            ⚙️
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-1.5 text-sm font-medium bg-[#3b82f6] text-white rounded-lg hover:bg-[#2563eb] transition-colors"
          >
            + 新建下载
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-700">
              <div className="text-5xl mb-3">📭</div>
              <p className="text-sm">暂无任务</p>
              <p className="text-xs mt-1 text-gray-800">点击「新建下载」添加</p>
            </div>
          ) : (
            <div className="space-y-2.5 max-w-[860px] mx-auto">
              {filtered.map((t) => (
                <TaskCard key={t.id} task={t} onChanged={reload} />
              ))}
            </div>
          )}
        </div>
      </main>

      {showAdd && <AddTaskDialog onClose={() => setShowAdd(false)} onAdded={reload} />}
      {showSet && <SettingsDialog onClose={() => setShowSet(false)} />}
    </div>
  );
}
