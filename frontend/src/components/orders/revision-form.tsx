"use client";

import Image from "next/image";
import { useState } from "react";
import { type Asset, roleLabels } from "@/types/orders";

export function RevisionForm({ base, inputs, disabled, onSubmit, onCancel }: {
  base: Asset; inputs: Asset[]; disabled: boolean;
  onSubmit: (body: unknown) => void; onCancel: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const actual = selected.map((id) => inputs.find((asset) => asset.id === id));
  const stale = actual.some((asset) => !asset);
  return <form className="revision-form" onSubmit={(event) => {
    event.preventDefault();
    if (stale) return;
    onSubmit({ base_asset_id: base.id, instruction: instruction.trim(), additional_inputs: actual.map((asset) => ({ asset_id: asset!.id, role: asset!.input_role })) });
  }}><h3>基于此图修改</h3>
    <div className="revision-base"><Image src={base.content_url} alt="本次修改基础图" width={160} height={160} unoptimized /><p>保留未要求修改的部分，沿用这张图的风格。每次生成 1 张，修改次数不限。</p></div>
    <fieldset className="order-form" disabled={disabled}>
      <label>本次修改要求<textarea required maxLength={2000} value={instruction} placeholder="例如：保留整体风格，去掉眼镜" onChange={(event) => setInstruction(event.target.value)} /></label>
      <p className="muted">基础图已占 1 张；可明确选择最多 3 张附加素材。当前选择 {1 + selected.length} / 4 张。</p>
      {inputs.map((asset) => <label className="check-label" key={asset.id}><input type="checkbox" checked={selected.includes(asset.id)} disabled={!selected.includes(asset.id) && selected.length >= 3} onChange={(event) => setSelected(event.target.checked ? [...selected, asset.id] : selected.filter((id) => id !== asset.id))} />{roleLabels[asset.input_role]} · {asset.original_name}</label>)}
      {stale && <p role="alert">附加素材已变更，请重新打开修改表单。</p>}
      <div className="order-actions"><button className="order-button primary" disabled={!instruction.trim() || stale}>生成一张修改图</button><button className="order-button" type="button" onClick={onCancel}>取消修改</button></div>
    </fieldset>
  </form>;
}
