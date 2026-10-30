/**
 * Coordinate conversion between PDF.js page CSS pixels and PDF points (spec 26).
 *
 * Inkstave's SyncTeX convention is PDF points (1/72 inch) with a **top-left**
 * page origin and y increasing downward — the same axis PDF.js viewport pixels
 * use — so the only conversion is the viewport `scale` factor.
 */
import type { SyncTexBox } from "./synctex";

/** A click at CSS offset (x, y) within a page -> PDF points (page-relative). */
export function cssToPdfPoint(xCss: number, yCss: number, scale: number): { h: number; v: number } {
  const s = scale || 1;
  return { h: xCss / s, v: yCss / s };
}

export interface CssRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * A SyncTeX box (baseline at `v`, extending `height` up and `depth` down) ->
 * an absolutely-positioned CSS rectangle within the page, in viewport pixels.
 * Dimensions are floored at 2px so a zero-size leaf still shows a marker.
 */
export function boxToCssRect(box: SyncTexBox, scale: number): CssRect {
  const s = scale || 1;
  return {
    left: box.h * s,
    top: (box.v - box.height) * s,
    width: Math.max(box.width * s, 2),
    height: Math.max((box.height + box.depth) * s, 2),
  };
}
