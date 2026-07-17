import type { Task } from "../types";
import { fmtBytes, fmtSpeed, fmtETA, STATUS_LABEL, STATUS_COLOR, ENGINE_LABEL, TYPE_ICON } from "../utils";
import { taskAction, deleteTask } from "../api";

function Btn({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 text-xs rounded border transition-colors ${
        danger
          ? "border-red-500/30 text-red-400 hover:border-red-500/60 hover:bg-red-500/10"
          : "border-gray-600 text-gray-400 hover:border-gray-500 hover:text-gray-200"
      }`}
    >
      {label}
    </button>
  );
}

export function TaskCard({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const isActive = task.status === "active";
  const isPaused = task.status === "paused";
  const isDone = task.status === "completed";
  const isFail = task.status === "failed";

  const barColor = isDone
    ? "from-green-500 to-green-600"
    : isFail
    ? "from-red-500 to-red-600"
    : "from-blue-500 to-cyan-500";

  const eta = task.size && task.speed ? (task.size - task.downloaded) / task.speed : -1;

  const act = (a: string) => { taskAction(task.id, a).then(onChanged); };
  const rm = () => { deleteTask(task.id).then(onChanged); };

  return (
    <div className="bg-[#1a1d24] border border-[#262a33] rounded-xl p-4 hover:border-[#3a4355] transition-colors">
      {/* header */}
      <div className="flex items-start justify-between mb-2.5 gap-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-base shrink-0">{TYPE_ICON[task.type] || "📄"}</span>
          <span className="font-semibold text-sm text-gray-100 truncate">{task.name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2a2f3a] text-gray-500">{ENGINE_LABEL[task.engine]}</span>
          <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${STATUS_COLOR[task.status]}`}>
            {STATUS_LABEL[task.status]}
          </span>
        </div>
      </div>

      {/* progress bar */}
      <div className="h-2 bg-[#2a2f3a] rounded-full overflow-hidden mb-2">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all duration-300`}
          style={{ width: `${Math.min(task.pct, 100)}%` }}
        />
      </div>

      {/* info row */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{task.pct.toFixed(1)}%</span>
        <span>{fmtBytes(task.downloaded)} / {fmtBytes(task.size)}</span>
        {isActive && <span>{fmtSpeed(task.speed)}</span>}
        {isActive && <span>ETA {fmtETA(eta)}</span>}
      </div>

      {/* error */}
      {isFail && task.error && (
        <div className="mt-2 text-xs text-red-400 truncate">{task.error}</div>
      )}

      {/* actions */}
      <div className="mt-3 flex gap-1.5">
        {isActive && <Btn label="⏸ 暂停" onClick={() => act("pause")} />}
        {(isPaused || isFail) && <Btn label="▶️ 恢复" onClick={() => act("resume")} />}
        {(isActive || isPaused) && <Btn label="✕ 取消" danger onClick={() => act("cancel")} />}
        {(isDone || isFail || task.status === "cancelled") && <Btn label="🗑 删除" danger onClick={rm} />}
      </div>
    </div>
  );
}
