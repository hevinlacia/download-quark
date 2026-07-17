import { useState, useEffect } from "react";
import { getSettings, saveSettings } from "../api";

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [outdir, setOutdir] = useState("");
  const [cookie, setCookie] = useState("");
  const [hasCookie, setHasCookie] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getSettings().then((d) => {
      setOutdir(d.outdir || "");
      setHasCookie(d.has_cookie);
    });
  }, []);

  async function save() {
    const body: { outdir?: string; cookie?: string } = { outdir };
    if (cookie.trim()) body.cookie = cookie.trim();
    const r = await saveSettings(body);
    if (r.ok) {
      setMsg("✅ 已保存");
      setHasCookie(true);
      setCookie("");
    } else {
      setMsg("❌ 保存失败");
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-[#1a1d24] border border-[#262a33] rounded-2xl p-6 w-[480px] max-w-[90vw]">
        <h3 className="text-base font-semibold mb-4 text-gray-100">⚙️ 设置</h3>

        <label className="block text-xs text-gray-500 mb-1.5">下载目录</label>
        <input
          value={outdir}
          onChange={(e) => setOutdir(e.target.value)}
          placeholder="如 /home/hevin/下载"
          className="w-full bg-[#0f1115] border border-[#2a2f3a] rounded-lg text-gray-100 p-2.5 text-sm mb-4 focus:outline-none focus:border-[#3b82f6]"
        />

        <label className="block text-xs text-gray-500 mb-1.5">夸克 Cookie</label>
        <textarea
          value={cookie}
          onChange={(e) => setCookie(e.target.value)}
          placeholder={hasCookie ? "已配置（留空不变）" : "粘贴夸克网盘完整 Cookie"}
          className="w-full bg-[#0f1115] border border-[#2a2f3a] rounded-lg text-gray-100 p-2.5 text-sm resize-y min-h-[60px] focus:outline-none focus:border-[#3b82f6]"
        />

        <div className="text-xs min-h-[16px] mt-2" style={{ color: msg.startsWith("✅") ? "#22c55e" : "#ef4444" }}>
          {msg}
        </div>

        <div className="flex gap-2 justify-end mt-3">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg bg-[#262a33] text-gray-400 hover:text-gray-200">
            关闭
          </button>
          <button onClick={save} className="px-4 py-2 text-sm rounded-lg bg-[#3b82f6] text-white font-medium hover:bg-[#2563eb]">
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
