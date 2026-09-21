"use client";

import { useState } from "react";
import type { GenerationTask } from "@/types/generation";

export function ReconcileForm({ task, disabled, onSubmit }: {
  task: GenerationTask; disabled: boolean; onSubmit: (path: string, body: unknown) => void;
}) {
  const [action, setAction] = useState("link_remote_task");
  const [remote, setRemote] = useState("");
  const [note, setNote] = useState("");
  const [risk, setRisk] = useState(false);
  return <details className="reconcile-form"><summary>核对这次提交</summary>
    <p className="muted">先在供应商后台核对。超时本身不能证明未受理；不要直接重新生成。</p>
    <form onSubmit={(event) => {
      event.preventDefault();
      if (disabled || note.trim().length < 5 || (action === "resubmit_with_risk" && !risk)) return;
      onSubmit(`/tasks/${task.id}/reconcile`, { action, note: note.trim(),
        provider_task_id: action === "link_remote_task" ? remote.trim() : null,
        acknowledge_possible_duplicate_charge: action === "resubmit_with_risk" && risk,
      });
    }}><fieldset disabled={disabled} className="order-form">
      <label>核对结果<select value={action} onChange={(e) => { setAction(e.target.value); setRisk(false); }}>
        <option value="link_remote_task">关联已找到的远端任务</option><option value="confirm_not_accepted">已确认供应商未受理</option><option value="resubmit_with_risk">接受可能重复计费，重新生成</option>
      </select></label>
      {action === "link_remote_task" && <label>供应商任务编号<input required maxLength={128} pattern="[a-zA-Z0-9_-]+" value={remote} onChange={(e) => setRemote(e.target.value)} /></label>}
      <label>核对依据<textarea required minLength={5} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="记录后台查询结果或客服确认依据" /></label>
      {action === "resubmit_with_risk" && <label className="risk-check"><input type="checkbox" required checked={risk} onChange={(e) => setRisk(e.target.checked)} />我接受旧请求可能已受理，重新生成可能重复计费</label>}
      <button className="order-button" disabled={note.trim().length < 5 || (action === "resubmit_with_risk" && !risk)}>记录核对结果</button>
    </fieldset></form>
  </details>;
}
