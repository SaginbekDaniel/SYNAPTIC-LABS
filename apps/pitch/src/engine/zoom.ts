export interface Rect { x: number; y: number; w: number; h: number } // fractions of the image
export interface View { s: number; x: number; y: number }

/**
 * Transform that fits an image (w x h px) into a W x H viewport, or zooms onto a region.
 * Zoom is capped (maxScale, in image pixels per screen pixel) so raster screenshots never get blurry-large.
 */
export function viewFor(W: number, H: number, w: number, h: number, rect?: Rect, maxScale = 1.25): View {
  const s0 = Math.min(W / w, H / h);
  if (!rect) return { s: s0, x: (W - w * s0) / 2, y: (H - h * s0) / 2 };
  const rw = rect.w * w, rh = rect.h * h;
  const s = Math.max(s0, Math.min((W / rw) * 0.92, (H / rh) * 0.92, maxScale));
  const iw = w * s, ih = h * s;
  const cx = W / 2 - (rect.x + rect.w / 2) * iw;
  const cy = H / 2 - (rect.y + rect.h / 2) * ih;
  const x = iw <= W ? (W - iw) / 2 : Math.min(0, Math.max(W - iw, cx));
  const y = ih <= H ? (H - ih) / 2 : Math.min(0, Math.max(H - ih, cy));
  return { s, x, y };
}
