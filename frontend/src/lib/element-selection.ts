import type { DetectedRegion } from "../types/orders.ts";

export function containsPixel(runs: number[], pixel: number): boolean {
  let low = 0, high = runs.length / 2 - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2), start = runs[middle * 2], size = runs[middle * 2 + 1];
    if (pixel < start) high = middle - 1;
    else if (pixel >= start + size) low = middle + 1;
    else return true;
  }
  return false;
}

export function hitElements(regions: DetectedRegion[], pixel: number): DetectedRegion[] {
  return regions.filter((r) => r.location_status === "located" && containsPixel(r.mask_runs ?? [], pixel))
    .sort((a, b) => Number(a.kind === "background") - Number(b.kind === "background")
      || (b.depth ?? 0) - (a.depth ?? 0) || (a.mask_area ?? 0) - (b.mask_area ?? 0));
}

export function imagePoint(clientX: number, clientY: number,
  rect: { left: number; top: number; width: number; height: number }, width: number, height: number,
): { x: number; y: number } | null {
  if (rect.width <= 0 || rect.height <= 0 || width <= 0 || height <= 0) return null;
  const x = (clientX - rect.left) / rect.width, y = (clientY - rect.top) / rect.height;
  if (x < 0 || y < 0 || x >= 1 || y >= 1) return null;
  return { x: Math.floor(x * width), y: Math.floor(y * height) };
}
