"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { apiGet, errorMessage } from "@/lib/api";
import { aspectSizes, type Asset, type ChangeItem, type OrderParams, type Style } from "@/types/orders";
import { CustomStyleEditor } from "./custom-style-editor";
import { StylePreviewAction } from "./style-preview-action";
import { previewBusy } from "@/lib/style-previews";

const stylePreviews: Record<string, string> = {
  q_crayon_001: "/styles/q-crayon-001-preview.png",
};

export function StyleCards({ selected, onSelect, disabled = false, manage = false }: {
  selected?: string | null; onSelect?: (id: string | null) => void; disabled?: boolean; manage?: boolean;
}) {
  const [styles, setStyles] = useState<Style[]>([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<Style | null>(null);
  const [editor, setEditor] = useState<{ style: Style | null } | null>(null);
  const [notice, setNotice] = useState("");
  const updateStyle = (saved: Style) => setStyles((current) => current.some((style) => style.style_id === saved.style_id)
    ? current.map((style) => style.style_id === saved.style_id ? saved : style) : [...current, saved]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      let repeat = manage;
      try {
        const data = await apiGet<{ items: Style[] }>("/styles", controller.signal);
        if (!controller.signal.aborted) { setStyles(data.items); setError(""); repeat ||= data.items.some(previewBusy); }
      } catch (cause) {
        if (!controller.signal.aborted) { setError(errorMessage(cause)); repeat = true; }
      }
      if (repeat && !controller.signal.aborted) timer = setTimeout(refresh, 3000);
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [manage]);
  return <div className="style-cards">
    {manage && <div className="style-original"><button type="button" className="order-button" onClick={() => { setDetail(null); setEditor({ style: null }); }}>＋ 新建自定义风格</button></div>}
    {notice && <p className="style-original" role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {onSelect && <div className="style-original"><button type="button" className="order-button" disabled={disabled} aria-pressed={selected === null} onClick={() => onSelect(null)}>保持原图风格</button></div>}
    {styles.map((style) => {
      const preview = style.cover_image || stylePreviews[style.style_id];
      const cover = <>
        <span className="style-cover">
          {preview ? <Image src={preview} width={216} height={216} sizes="216px" unoptimized={!!style.cover_image} alt={`${style.style_name}风格示意图`} /> : <span className="style-custom-cover"><span aria-hidden="true">Aa</span><span>自定义风格</span><small>文字提示词 · 无示意图</small></span>}
          {(preview || previewBusy(style) || style.preview?.status === "failed" || style.preview?.status === "submission_unknown") && <span className="style-cover-label">{previewBusy(style) ? "示意图生成中…" : style.preview?.status === "submission_unknown" ? "提交结果待核对" : style.preview?.status === "failed" ? "生成失败 · 可重试" : style.cover_stale ? "提示词已修改 · 封面待更新" : "风格示意"}</span>}
        </span>
      </>;
      const name = <span className="style-name" title={style.style_name}>{style.style_name}</span>;
      const description = style.preview?.error_message || style.description;
      return <article className={`style-card ${selected === style.style_id ? "selected" : ""}`} key={style.style_id}>
      {onSelect ? <button className="style-card-content" type="button" disabled={disabled} aria-pressed={selected === style.style_id} onClick={() => onSelect(style.style_id)}>
        {cover}{name}{description && <span className="style-description" title={description}>{description}</span>}
      </button> : <div className="style-card-content">{cover}<div className="style-title-row">{name}{manage && !style.is_builtin && <StylePreviewAction style={style} onUpdated={updateStyle} onMessage={setNotice} />}</div>{description && <span className="style-description" title={description}>{description}</span>}</div>}
      <button className="text-button" type="button" onClick={() => setDetail(style)}>查看提示词</button>
    </article>;
    })}
    {detail && <dialog open className="style-dialog" aria-label="风格基础提示词">
      <h3>{detail.style_name}</h3>
      <p>{detail.is_builtin ? "内置风格提示词，只读。" : "自定义风格提示词。"}{!manage && "本次生成的完整要求请在配置下方预览。"}</p>
      <pre className="prompt-preview">{Object.values(detail.prompt_template).join("\n")}</pre>
      {manage && !detail.is_builtin && <button type="button" className="order-button" onClick={() => { setEditor({ style: detail }); setDetail(null); }}>编辑自定义风格</button>}
      <button type="button" className="order-button" onClick={() => setDetail(null)}>关闭</button>
    </dialog>}
    {editor && <CustomStyleEditor style={editor.style} onCancel={() => setEditor(null)} onSaved={(saved) => {
      updateStyle(saved);
      setEditor(null); setNotice("自定义风格已保存，可在订单中选择使用。");
    }} />}
  </div>;
}

export function CreationFields({ config, assets, disabled, onChange, section = "all" }: {
  config: OrderParams; assets: Asset[]; disabled: boolean; onChange: (value: OrderParams) => void;
  section?: "all" | "base" | "changes";
}) {
  const base = assets.find((asset) => asset.id === config.base_asset_id);
  const materials = assets.filter((asset) => asset.kind === "input" && asset.is_active_input && asset.input_role === "material");
  const patch = (value: Partial<OrderParams>) => onChange({ ...config, ...value });
  const changeItem = (index: number, value: Partial<ChangeItem>) => patch({ changes: config.changes.map((item, i) => i === index ? { ...item, ...value } : item) });
  const selected = new Set(config.changes.flatMap((item) => item.source_asset_ids));
  const stale = [...selected].some((id) => !materials.some((asset) => asset.id === id));
  return <fieldset className="order-form" disabled={disabled}>
    {section !== "changes" && <><label>本次编辑底图{base?.kind === "generated" ? <strong>结果版本 · {base.id.slice(0, 8)}</strong> : <select value={config.base_asset_id ?? ""} onChange={(event) => patch({ base_asset_id: event.target.value || null })}>
      <option value="">请选择主照片</option>{assets.filter((asset) => asset.kind === "input" && asset.is_active_input && asset.input_role === "main").map((asset) => <option key={asset.id} value={asset.id}>{asset.original_name}</option>)}
    </select>}</label>
    {base && <a href={base.content_url} target="_blank" rel="noreferrer"><Image src={base.content_url} width={240} height={180} unoptimized className="creation-base" alt="本次编辑底图" /></a>}
    <p className="muted">未指定修改的内容默认保留，包括人物和物品数量、布局、动作与背景。</p>
    <h3>风格表现</h3><StyleCards selected={config.style_id} disabled={disabled} onSelect={(style_id) => patch({ style_id })} /></>}
    {section !== "base" && <><h3>修改项（可选）</h3><p className="muted">左右以画面视角描述。只换风格时无需添加修改项或素材。</p>
    {config.changes.map((item, index) => <fieldset key={index} className="change-item">
      <legend>修改 {index + 1}</legend>
      <label>目标对象或部位<input required maxLength={100} value={item.target_description} onChange={(event) => changeItem(index, { target_description: event.target.value })} placeholder="画面左侧人物的脸部" /></label>
      <label>修改用途<input required maxLength={100} list="change-types" value={item.change_type} onChange={(event) => changeItem(index, { change_type: event.target.value })} /></label>
      <label>具体要求<textarea required maxLength={2000} value={item.instruction} onChange={(event) => changeItem(index, { instruction: event.target.value })} /></label>
      <div>素材来源（可选，可多选）{materials.map((asset) => <label className="check-label" key={asset.id}><input type="checkbox" checked={item.source_asset_ids.includes(asset.id)} onChange={(event) => changeItem(index, { source_asset_ids: event.target.checked ? [...item.source_asset_ids, asset.id] : item.source_asset_ids.filter((id) => id !== asset.id) })} />{asset.original_name}</label>)}</div>
      {item.source_asset_ids.filter((id) => !materials.some((asset) => asset.id === id)).map((id) => <p className="order-alert" key={id}>素材已失效：{id} <button type="button" onClick={() => changeItem(index, { source_asset_ids: item.source_asset_ids.filter((key) => key !== id) })}>解除此引用</button></p>)}
      <label>保留要求<textarea maxLength={2000} value={item.preserve_instruction} onChange={(event) => changeItem(index, { preserve_instruction: event.target.value })} placeholder="保留底图表情、朝向和身体姿态" /></label>
      <button className="text-button" type="button" onClick={() => patch({ changes: config.changes.filter((_, i) => i !== index) })}>移除此修改项</button>
    </fieldset>)}
    <datalist id="change-types">{["脸部身份", "发型", "手势", "服装", "道具"].map((value) => <option key={value} value={value} />)}</datalist>
    <button type="button" className="order-button" disabled={config.changes.length >= 20} onClick={() => patch({ changes: [...config.changes, { target_description: "", change_type: "", source_asset_ids: [], instruction: "", preserve_instruction: "" }] })}>＋ 添加修改项</button>
    {stale && <p className="order-alert">有失效素材，请修正引用后保存。</p>}
    <label>补充要求与取景<textarea rows={3} maxLength={2000} value={config.extra_requirement} onChange={(event) => patch({ extra_requirement: event.target.value })} placeholder="例如：裁掉画面中的手部，保留面部和发型；不重新设计姿势" /></label>
    <label>输出比例<select value={config.aspect_ratio} onChange={(event) => patch({ aspect_ratio: event.target.value })}>{Object.entries(aspectSizes).map(([ratio, size]) => <option key={ratio} value={ratio}>{ratio} · {size}</option>)}</select></label>
    <label>生图格式<select value={config.output_format ?? "png"} onChange={(event) => patch({ output_format: event.target.value as "png" | "jpeg" | "webp" })}><option value="png">PNG</option><option value="jpeg">JPEG</option><option value="webp">WebP</option></select></label>
    <p className="muted">每次固定一张。尺寸对应供应商文档，最终以实际返回为准。比例控制画布，取景请写入补充要求。</p>
    {base && <p className="muted">底图 {base.width} × {base.height}；比例变化可能需要裁剪或扩展画布，不会要求拉伸原图。</p>}</>}
  </fieldset>;
}
