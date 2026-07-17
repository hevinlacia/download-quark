import { useState } from "react";
import { createTask, createTorrent } from "../api";

type Tab = "url" | "quark" | "torrent";

export function AddTaskDialog({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [tab, setTab] = useState<Tab>("url");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setMsg("");
    try {
      if (tab === "url") {
        const lines = text.trim().split(/[\n\s]+/).filter(Boolean);
        if (!lines.length) { setMsg("请输入链接"); setBusy(false); return; }
        for (const u of lines) {
          const r = await createTask({ type: u.startsWith("magnet:") ? "magnet" : "url", uri: u });
          if (!r.ok) { setMsg(`❌ ${u.slice(0, 30)}...: ${r.error}`); setBusy(false); return; }
        }
      } else if (tab === "quark") {
        const fids = text.trim().split(/[\n\s]+/).filter(Boolean);
        if (!fids.length) { setMsg("请输入 fid"); setBusy(false); return; }
        for (const f of fids) {
          const r = await createTask({ type: "quark", fid: f });
          if (!r.ok) { setMsg(`❌ ${f}: ${r.error}`); setBusy(false); return; }
        }
      } else if (tab === "torrent") {
        if (!file) { setMsg("请选择 .torrent 文件"); setBusy(false); return; }
        const r = await createTorrent(file);
        if (!r.ok) { setMsg(`❌ ${r.error}`); setBusy(false); return; }
      }
      setMsg("✅ 已添加");
      setText("");
      setFile(null);
      setTimeout(() => { onAdded(); onClose(); }, 600);
    } catch (e) {
      setMsg(`❌ ${e}`);
    }
    setBusy(false);
  }

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "url", label: "URL / 磁力", icon: "🔗" },
    { key: "quark", label: "夸克网盘", icon: "☁️" },
    { key: "torrent", label: "种子文件", icon: "🌊" },
  ];

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-[#1a1d24] border border-[#262a33] rounded-2xl p-6 w-[480px] max-w-[90vw]">
        <h3 className="text-base font-semibold mb-4 text-gray-100">新建下载</h3>

        {/* tabs */}
        <div className="flex gap-1 mb-4 bg-[#0f1115] p-1 rounded-lg">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 py-1.5 px-2 text-xs rounded-md transition-colors ${
                tab === t.key ? "bg-[#262a33] text-gray-100" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* input */}
        {tab === "torrent" ? (
          <div
            className="border-2 border-dashed border-[#2a2f3a] rounded-lg p-8 text-center cursor-pointer hover:border-[#3a4355] transition-colors"
            onClick={() => document.getElementById("torrent-input")?.click()}
          >
            <input
              id="torrent-input"
              type="file"
              accept=".torrent"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <div className="text-3xl mb-2">🌊</div>
            <div className="text-sm text-gray-400">{file ? file.name : "点击选择 .torrent 文件"}</div>
          </div>
        ) : (
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={tab === "url" ? "粘贴 URL 或磁力链接（多个用换行分隔）…" : "粘贴夸克文件 fid（多个用空格/换行分隔）…"}
            className="w-full bg-[#0f1115] border border-[#2a2f3a] rounded-lg text-gray-100 p-3 text-sm resize-y min-h-[80px] focus:outline-none focus:border-[#3b82f6]"
          />
        )}

        <div className="text-xs text-red-400 min-h-[16px] mt-2">{msg}</div>

        <div className="flex gap-2 justify-end mt-3">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg bg-[#262a33] text-gray-400 hover:text-gray-200">
            取消
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="px-4 py-2 text-sm rounded-lg bg-[#3b82f6] text-white font-medium hover:bg-[#2563eb] disabled:opacity-50"
          >
            {busy ? "添加中…" : "开始下载"}
          </button>
        </div>
      </div>
    </div>
  );
}
