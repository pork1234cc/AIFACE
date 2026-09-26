"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { hitElements, imagePoint } from "@/lib/element-selection";
import type { Asset, DetectedRegion, RegionDetection } from "@/types/orders";

type Mode = "select" | "include" | "exclude";
type Props = {
  base: Asset; detection: RegionDetection | null; selected: string; disabled: boolean;
  onSelect: (region: DetectedRegion) => void;
  onRefine: (x: number, y: number, label: number) => void;
};

function ElementCanvas({ base, detection, selected, disabled, onSelect, onRefine, mode, large = false, zoom = 1 }: Props & {
  mode: Mode; large?: boolean; zoom?: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState("");
  const [candidates, setCandidates] = useState<DetectedRegion[]>([]);
  const width = detection?.width ?? base.width, height = detection?.height ?? base.height;
  const active = detection?.regions.find((r) => r.id === (mode === "select" ? hover || selected : selected));

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, width, height);
    if (!active?.mask_runs?.length) return;
    const pixels = context.createImageData(width, height);
    const runs = active.mask_runs;
    for (let n = 0; n < runs.length; n += 2) {
      for (let index = runs[n]; index < runs[n] + runs[n + 1]; index++) {
        pixels.data.set([49, 139, 93, 88], index * 4);
      }
    }
    // 边界加深，内部半透明，保留原图细节。
    for (let n = 0; n < runs.length; n += 2) {
      for (let i = runs[n]; i < runs[n] + runs[n + 1]; i++) {
        if (i < width || i >= width * (height - 1) || i % width === 0 || i % width === width - 1
          || !pixels.data[(i - 1) * 4 + 3] || !pixels.data[(i + 1) * 4 + 3]
          || !pixels.data[(i - width) * 4 + 3] || !pixels.data[(i + width) * 4 + 3]) pixels.data[i * 4 + 3] = 220;
      }
    }
    context.putImageData(pixels, 0, 0);
  }, [active, width, height]);

  return <div className="element-canvas-group">
    <div className={large ? "element-scroll element-scroll-large" : "element-scroll"}>
      <button type="button" className="region-photo element-photo" disabled={disabled || !detection}
        style={{ aspectRatio: `${base.width} / ${base.height}`, ...(large ? { width: `${Math.min(base.width, 1000) * zoom}px`, maxWidth: "none" } : {}) }}
        aria-label="点击照片选择元素"
        onMouseLeave={() => setHover("")}
        onMouseMove={(event) => {
          if (!detection || mode !== "select") return;
          const point = imagePoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), width, height);
          const matches = point ? hitElements(detection.regions, point.y * width + point.x) : [];
          setHover(matches[0]?.id ?? "");
        }}
        onClick={(event) => {
          if (!detection) return;
          const point = imagePoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), width, height);
          if (!point) return;
          if (mode !== "select") { onRefine(point.x / width * 1000, point.y / height * 1000, mode === "include" ? 1 : 0); return; }
          const matches = hitElements(detection.regions, point.y * width + point.x);
          setCandidates(matches);
          if (matches[0]) onSelect(matches[0]);
        }}>
        <Image src={base.content_url} alt="元素选择预览" fill unoptimized sizes={large ? "1000px" : "320px"} />
        <canvas ref={canvas} width={width} height={height} aria-hidden="true" />
      </button>
    </div>
    <div className="element-hover-name" aria-live="polite">{active?.label || "移动鼠标查看元素轮廓"}</div>
    {candidates.length > 1 && <div className="element-candidates"><span>此处还可以选择：</span>{candidates.map((r) =>
      <button type="button" className="text-button" key={r.id} disabled={disabled} onClick={() => onSelect(r)}>{r.label}</button>)}</div>}
  </div>;
}

export function ElementPhoto(props: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<Mode>("select");
  const [zoom, setZoom] = useState(1);
  const selected = props.detection?.regions.find((r) => r.id === props.selected);
  const parent = props.detection?.regions.find((r) => r.id === selected?.parent_id);
  const toolbar = <div className="element-toolbar">
    <button type="button" className="region-chip" aria-pressed={mode === "select"} onClick={() => setMode("select")}>点选元素</button>
    <button type="button" className="region-chip" aria-pressed={mode === "include"} disabled={!selected || props.disabled} onClick={() => setMode("include")}>补选范围</button>
    <button type="button" className="region-chip" aria-pressed={mode === "exclude"} disabled={!selected || props.disabled} onClick={() => setMode("exclude")}>排除范围</button>
    {parent && <button type="button" className="text-button" disabled={props.disabled} onClick={() => props.onSelect(parent)}>选择上级：{parent.label}</button>}
  </div>;
  return <div className="element-photo-editor">
    <ElementCanvas {...props} mode={mode} />
    <button type="button" className="text-button" onClick={() => dialog.current?.showModal()}>放大点选</button>
    {toolbar}
    {mode !== "select" && <p className="region-note">{mode === "include" ? "点击应包含在当前元素里的位置。" : "点击不属于当前元素的位置。"}每次点击后更新选区。</p>}
    {selected?.location_status === "unlocated" && <p className="region-note">此元素尚未可靠定位，可用“补选范围”修正。</p>}
    <dialog ref={dialog} className="element-dialog">
      <div className="element-dialog-header"><strong>放大点选元素</strong><button type="button" className="text-button" onClick={() => dialog.current?.close()}>关闭</button></div>
      {toolbar}
      <label className="element-zoom">缩放 <input type="range" min="0.5" max="2" step="0.25" value={zoom} onChange={(e) => setZoom(Number(e.target.value))} /> {Math.round(zoom * 100)}%</label>
      <ElementCanvas {...props} mode={mode} large zoom={zoom} />
    </dialog>
  </div>;
}
