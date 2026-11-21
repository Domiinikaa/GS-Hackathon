/*!
 * Liquid Glass refraction, React hook.
 *
 * Ported from the Angular directive in stormaref/LiquidGlassSkill, whose
 * refraction field is a port of the fragment shader in liquid-glass-js
 * (https://github.com/dashersw/liquid-glass-js) - Copyright (c) 2025 Armagan
 * Amcalar, MIT. Permission is hereby granted, free of charge, to any person
 * obtaining a copy of that software to deal in it without restriction,
 * provided this notice travels with it; it is provided "as is", without
 * warranty of any kind. Keep this header on any copy or port.
 *
 * Usage: const ref = useLiquidGlass<HTMLDivElement>();
 *        <div ref={ref} className="glass">...</div>
 * Returns a callback ref, so it also works for elements rendered later.
 *
 * The backdrop bends through the element's rounded edge via an SVG
 * displacement filter used as `backdrop-filter: url(#id)`. That only renders
 * in Chromium; elsewhere the hook does nothing and the CSS blur stays.
 */
import { useEffect, useState } from 'react';

export interface LiquidGlassConfig {
  edgeIntensity: number;
  rimIntensity: number;
  baseIntensity: number;
  edgeDistance: number;
  rimDistance: number;
  baseDistance: number;
  cornerBoost: number;
  rippleEffect: number;
  blurRadius: number;
  /** Center distortion; off keeps the middle legible. */
  warp: boolean;
}

const GLASS_PRESET: LiquidGlassConfig = {
  edgeIntensity: 0.015,
  rimIntensity: 0.028,
  baseIntensity: 0.05,
  edgeDistance: 0.5,
  rimDistance: 1.7,
  baseDistance: 0.2,
  cornerBoost: 0.06,
  rippleEffect: 0.26,
  blurRadius: 2,
  warp: false,
};

/** Bake the map at 2x so the 1-2px rim band stays crisp. */
const SUPERSAMPLE = 2;
/** Cap the baked map's longest edge to bound bake time and data-URL size. */
const MAX_MAP_EDGE = 1400;
/** feGaussianBlur stdDeviation per unit of blurRadius (fit to the library). */
const BLUR_STD_PER_RADIUS = 0.35;
const SVG_NS = 'http://www.w3.org/2000/svg';

interface FilterEntry {
  id: string;
  node: SVGFilterElement;
  refs: number;
}

const filters = new Map<string, FilterEntry>();
let defs: SVGSVGElement | null = null;
let nextId = 0;

/** SVG backdrop filters are Chromium-only and can't be feature-detected. */
function isSupported(): boolean {
  const brands = (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } })
    .userAgentData?.brands;
  if (brands) return brands.some((b) => /Chromium|Google Chrome|Microsoft Edge/i.test(b.brand));
  return /Chrome\//.test(navigator.userAgent);
}

function prefersReducedTransparency(): boolean {
  return window.matchMedia?.('(prefers-reduced-transparency: reduce)').matches ?? false;
}

export function useLiquidGlass<T extends HTMLElement>(config?: Partial<LiquidGlassConfig>) {
  const [host, setHost] = useState<T | null>(null);
  const configKey = JSON.stringify(config ?? {});

  useEffect(() => {
    if (!host || !isSupported() || prefersReducedTransparency()) return;

    const cfg: LiquidGlassConfig = { ...GLASS_PRESET, ...(config ?? {}) };
    let currentKey: string | null = null;
    let frame = 0;
    let debounce: number | undefined;

    const release = () => {
      if (!currentKey) return;
      const entry = filters.get(currentKey);
      currentKey = null;
      if (entry && --entry.refs <= 0) {
        filters.delete(entry.node.dataset.key ?? '');
        entry.node.remove();
      }
    };

    const rebuild = () => {
      const w = Math.round(host.offsetWidth);
      const h = Math.round(host.offsetHeight);
      if (w < 2 || h < 2) return;
      const radius = Math.min(
        resolveRadius(getComputedStyle(host).borderTopLeftRadius, w, h),
        Math.min(w, h) / 2,
      );
      // The shader displaces in fractions of the page; the live equivalent is the viewport.
      const pageW = window.innerWidth;
      const pageH = window.innerHeight;
      const key = [w, h, radius, pageW, pageH, JSON.stringify(cfg)].join('|');
      if (key === currentKey) return;
      release();
      const entry = acquireFilter(key, w, h, radius, pageW, pageH, cfg);
      currentKey = key;
      host.style.backdropFilter = `url(#${entry.id})`;
    };

    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(rebuild);
    };
    const onWindowResize = () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(schedule, 180);
    };

    const observer = new ResizeObserver(schedule);
    observer.observe(host);
    window.addEventListener('resize', onWindowResize, { passive: true });
    schedule();

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', onWindowResize);
      window.clearTimeout(debounce);
      cancelAnimationFrame(frame);
      release();
      host.style.backdropFilter = '';
    };
    // configKey stands in for config so a new object literal each render is fine
  }, [host, configKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return setHost;
}

/** Same-size elements (a list of equal cards) share one filter. */
function acquireFilter(
  key: string,
  w: number,
  h: number,
  radius: number,
  pageW: number,
  pageH: number,
  cfg: LiquidGlassConfig,
): FilterEntry {
  const existing = filters.get(key);
  if (existing && existing.node.isConnected) {
    existing.refs++;
    return existing;
  }
  if (existing) filters.delete(key);

  const { mapUrl, scale } = buildDisplacementMap(w, h, radius, pageW, pageH, cfg);
  const id = `liquid-glass-${nextId++}`;

  const filter = document.createElementNS(SVG_NS, 'filter');
  filter.setAttribute('id', id);
  // The region must extend past the box by the max displacement plus blur spread,
  // or the refraction clips to transparent at the corners.
  const marginPx = scale / 2 + 3 * cfg.blurRadius * BLUR_STD_PER_RADIUS;
  const mx = (marginPx / w) * 100;
  const my = (marginPx / h) * 100;
  filter.setAttribute('x', `${-mx}%`);
  filter.setAttribute('y', `${-my}%`);
  filter.setAttribute('width', `${100 + 2 * mx}%`);
  filter.setAttribute('height', `${100 + 2 * my}%`);
  filter.setAttribute('color-interpolation-filters', 'sRGB');
  filter.dataset.key = key;

  const feImage = document.createElementNS(SVG_NS, 'feImage');
  feImage.setAttribute('href', mapUrl);
  feImage.setAttribute('x', '0');
  feImage.setAttribute('y', '0');
  feImage.setAttribute('width', String(w));
  feImage.setAttribute('height', String(h));
  feImage.setAttribute('preserveAspectRatio', 'none');
  feImage.setAttribute('result', 'map');

  const feDisplacement = document.createElementNS(SVG_NS, 'feDisplacementMap');
  feDisplacement.setAttribute('in', 'SourceGraphic');
  feDisplacement.setAttribute('in2', 'map');
  feDisplacement.setAttribute('scale', String(scale));
  feDisplacement.setAttribute('xChannelSelector', 'R');
  feDisplacement.setAttribute('yChannelSelector', 'G');
  feDisplacement.setAttribute('result', 'displaced');

  const feBlur = document.createElementNS(SVG_NS, 'feGaussianBlur');
  feBlur.setAttribute('in', 'displaced');
  feBlur.setAttribute('stdDeviation', String(cfg.blurRadius * BLUR_STD_PER_RADIUS));

  filter.append(feImage, feDisplacement, feBlur);
  ensureDefs().querySelector('defs')!.appendChild(filter);

  const entry = { id, node: filter, refs: 1 };
  filters.set(key, entry);
  return entry;
}

function ensureDefs(): SVGSVGElement {
  if (!defs || !defs.isConnected) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', '0');
    svg.setAttribute('height', '0');
    svg.setAttribute('aria-hidden', 'true');
    svg.style.position = 'fixed';
    svg.appendChild(document.createElementNS(SVG_NS, 'defs'));
    document.body.appendChild(svg);
    defs = svg;
  }
  return defs;
}

/**
 * Bake the shader's refraction field into a displacement map: R/G encode the
 * x/y sample offset around neutral 128, scaled to the feDisplacementMap `scale`.
 */
function buildDisplacementMap(
  w: number,
  h: number,
  radius: number,
  pageW: number,
  pageH: number,
  cfg: LiquidGlassConfig,
): { mapUrl: string; scale: number } {
  const ss = Math.max(0.25, Math.min(SUPERSAMPLE, MAX_MAP_EDGE / Math.max(w, h)));
  const bw = Math.max(1, Math.round(w * ss));
  const bh = Math.max(1, Math.round(h * ss));
  const r = radius * ss;
  const minDim = Math.min(w, h);
  const dx = new Float32Array(bw * bh);
  const dy = new Float32Array(bw * bh);
  let maxAbs = 0;

  for (let py = 0; py < bh; py++) {
    for (let px = 0; px < bw; px++) {
      const cx = (px + 0.5) / bw;
      const cy = (py + 0.5) / bh;

      // Signed distance to the rounded-rect edge, in CSS px.
      const tx = Math.abs(px + 0.5 - bw / 2) - (bw / 2 - r);
      const ty = Math.abs(py + 0.5 - bh / 2) - (bh / 2 - r);
      const outside = Math.hypot(Math.max(tx, 0), Math.max(ty, 0));
      const inside = Math.min(Math.max(tx, ty), 0);
      const distPx = Math.max(-(outside + inside - r), 0) / ss;

      const edgeFall = Math.exp(-distPx * cfg.edgeDistance);
      const rimFall = Math.exp(-distPx * cfg.rimDistance);
      const baseFall = 1 - Math.exp(-distPx * cfg.baseDistance);
      const baseComponent = cfg.warp ? baseFall * cfg.baseIntensity : 0;
      const total = baseComponent + edgeFall * cfg.edgeIntensity + rimFall * cfg.rimIntensity;

      let nx = cx - 0.5;
      let ny = cy - 0.5;
      const len = Math.hypot(nx, ny);
      if (len > 0) {
        nx /= len;
        ny /= len;
      }

      const cornerNorm = Math.max(Math.min(cx, 1 - cx), Math.min(cy, 1 - cy)) * minDim;
      const corner = Math.exp(-cornerNorm * 0.3) * cfg.cornerBoost;
      const ripple = Math.sin((distPx / minDim) * 25) * cfg.rippleEffect * rimFall;

      const fx = (nx * (total + corner) - ny * ripple) * pageW;
      const fy = (ny * (total + corner) + nx * ripple) * pageH;

      const i = py * bw + px;
      dx[i] = fx;
      dy[i] = fy;
      maxAbs = Math.max(maxAbs, Math.abs(fx), Math.abs(fy));
    }
  }

  const scale = Math.max(maxAbs * 2, 1e-4);
  // feDisplacementMap decodes b as scale*(b/255 - 0.5); 128 is not exactly neutral,
  // so pre-subtract that bias to keep zero displacement in place.
  const bias = scale * (128 / 255 - 0.5);
  const canvas = document.createElement('canvas');
  canvas.width = bw;
  canvas.height = bh;
  const ctx = canvas.getContext('2d')!;
  const image = ctx.createImageData(bw, bh);
  const data = image.data;
  for (let i = 0; i < bw * bh; i++) {
    data[i * 4] = clampByte(255 * (0.5 + (dx[i] - bias) / scale));
    data[i * 4 + 1] = clampByte(255 * (0.5 + (dy[i] - bias) / scale));
    data[i * 4 + 2] = 128;
    data[i * 4 + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
  return { mapUrl: canvas.toDataURL('image/png'), scale };
}

function resolveRadius(computed: string, w: number, h: number): number {
  const value = parseFloat(computed) || 0;
  return computed.trim().endsWith('%') ? (value / 100) * Math.min(w, h) : value;
}

function clampByte(v: number): number {
  return Math.max(0, Math.min(255, Math.round(v)));
}
