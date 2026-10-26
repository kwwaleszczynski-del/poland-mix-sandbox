// Small canvas charts for the page: a stacked area (dispatch of one week) and line charts (price, duration
// curves), with a crosshair tooltip. Colours come from CSS custom properties, so redrawing after a theme change
// is enough to follow light and dark mode.

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function niceStep(range, target) {
  const raw = range / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const f = raw / mag;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
}

export function ticks(min, max, target = 5) {
  if (!(max > min)) return [min];
  const step = niceStep(max - min, target);
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(Math.round(v / step) * step + 0);
  return out;
}

function hatch(ctx, color) {
  const c = document.createElement("canvas");
  const dpr = window.devicePixelRatio || 1;
  c.width = c.height = Math.round(6 * dpr);
  const g = c.getContext("2d");
  g.scale(dpr, dpr);
  g.strokeStyle = color;
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(-1, 7); g.lineTo(7, -1);
  g.moveTo(-1, 1); g.lineTo(1, -1);
  g.moveTo(5, 7); g.lineTo(7, 5);
  g.stroke();
  const p = ctx.createPattern(c, "repeat");
  if (p && p.setTransform) p.setTransform(new DOMMatrix().scale(1 / dpr));
  return p;
}

export class Chart {
  // opts: { height, kind: "stack" | "line", yFormat, xTicks(n, width) -> [{i, label}], tooltip(i) -> html, yMax, yMin }
  constructor(container, opts) {
    this.el = container;
    this.opts = opts;
    this.canvas = document.createElement("canvas");
    this.tip = document.createElement("div");
    this.tip.className = "tooltip";
    this.el.append(this.canvas, this.tip);
    this.hover = -1;
    this.data = null;
    const move = (ev) => {
      if (!this.data) return;
      const r = this.canvas.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const i = Math.round((x - this.pad.l) / this.plotW * (this.n - 1));
      this.hover = i >= 0 && i < this.n ? i : -1;
      this.draw();
      this.showTip(x, ev.clientY - r.top);
    };
    this.canvas.addEventListener("pointermove", move);
    this.canvas.addEventListener("pointerdown", move);
    this.canvas.addEventListener("pointerleave", () => { this.hover = -1; this.tip.style.display = "none"; this.draw(); });
    new ResizeObserver(() => this.draw()).observe(this.el);
  }

  set(data) { this.data = data; this.draw(); }

  showTip(x, y) {
    if (this.hover < 0 || !this.opts.tooltip) { this.tip.style.display = "none"; return; }
    this.tip.innerHTML = this.opts.tooltip(this.hover);
    this.tip.style.display = "block";
    const w = this.tip.offsetWidth, h = this.tip.offsetHeight, W = this.el.clientWidth;
    let left = x + 14;
    if (left + w > W) left = Math.max(0, x - w - 14);
    this.tip.style.left = `${left}px`;
    this.tip.style.top = `${Math.max(0, Math.min(y - h / 2, this.height - h))}px`;
  }

  draw() {
    if (!this.data) return;
    const dpr = window.devicePixelRatio || 1;
    const W = this.el.clientWidth;
    const H = this.height = this.opts.height;
    if (W <= 0) return;
    this.canvas.width = Math.round(W * dpr);
    this.canvas.height = Math.round(H * dpr);
    this.canvas.style.height = `${H}px`;
    const ctx = this.canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const pad = this.pad = { l: 46, r: 10, t: 8, b: 24 };
    const plotW = this.plotW = W - pad.l - pad.r;
    const plotH = H - pad.t - pad.b;
    const d = this.data;
    const n = this.n = d.n;

    // value range
    let lo = this.opts.yMin ?? 0, hi = 0;
    if (this.opts.kind === "stack") {
      for (let i = 0; i < n; i++) {
        let up = 0, down = 0;
        for (const l of d.up) up += l.values[i];
        for (const l of d.down) down += l.values[i];
        if (d.line) up = Math.max(up, d.line.values[i]);
        hi = Math.max(hi, up);
        lo = Math.min(lo, -down);
      }
    } else {
      for (const s of d.series) for (let i = 0; i < n; i++) { hi = Math.max(hi, s.values[i]); lo = Math.min(lo, s.values[i]); }
    }
    if (this.opts.yMax !== undefined) hi = Math.min(hi, this.opts.yMax);
    if (hi <= lo) hi = lo + 1;
    const yt = ticks(lo, hi, Math.max(3, Math.round(plotH / 55)));
    lo = Math.min(lo, yt[0]);
    hi = Math.max(hi, yt[yt.length - 1]);
    const X = (i) => pad.l + (n <= 1 ? 0 : i / (n - 1) * plotW);
    const Y = (v) => pad.t + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * plotH;

    // grid and axes
    ctx.font = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
    ctx.fillStyle = cssVar("--muted");
    ctx.strokeStyle = cssVar("--grid");
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const v of yt) {
      const y = Math.round(Y(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.fillText(this.opts.yFormat ? this.opts.yFormat(v) : String(v), pad.l - 6, y);
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const t of this.opts.xTicks(n, plotW)) ctx.fillText(t.label, X(t.i), H - pad.b + 6);
    ctx.strokeStyle = cssVar("--axis");
    ctx.beginPath(); ctx.moveTo(pad.l, Math.round(Y(0)) + 0.5); ctx.lineTo(W - pad.r, Math.round(Y(0)) + 0.5); ctx.stroke();

    const surface = cssVar("--surface");
    if (this.opts.kind === "stack") {
      const area = (layers, sign) => {
        const base = new Float64Array(n);
        for (const l of layers) {
          const top = new Float64Array(n);
          for (let i = 0; i < n; i++) top[i] = base[i] + l.values[i];
          let any = false;
          for (let i = 0; i < n; i++) if (l.values[i] > 0.5) { any = true; break; }
          if (any) {
            ctx.beginPath();
            for (let i = 0; i < n; i++) ctx.lineTo(X(i), Y(sign * top[i]));
            for (let i = n - 1; i >= 0; i--) ctx.lineTo(X(i), Y(sign * base[i]));
            ctx.closePath();
            ctx.fillStyle = l.hatch ? hatch(ctx, cssVar(l.color)) : cssVar(l.color);
            ctx.fill();
            // surface-coloured edge = the gap between neighbouring layers
            ctx.beginPath();
            for (let i = 0; i < n; i++) ctx.lineTo(X(i), Y(sign * top[i]));
            ctx.strokeStyle = surface;
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }
          base.set(top);
        }
      };
      area(d.up, 1);
      area(d.down, -1);
      if (d.line) {
        ctx.beginPath();
        for (let i = 0; i < n; i++) ctx.lineTo(X(i), Y(d.line.values[i]));
        ctx.strokeStyle = cssVar("--ink");
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.stroke();
      }
    } else {
      for (const s of d.series) {
        ctx.beginPath();
        for (let i = 0; i < n; i++) ctx.lineTo(X(i), Y(s.values[i]));
        ctx.strokeStyle = cssVar(s.color);
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.stroke();
      }
    }
    if (this.hover >= 0) {
      const x = Math.round(X(this.hover)) + 0.5;
      ctx.strokeStyle = cssVar("--ink-2");
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + plotH); ctx.stroke();
      if (this.opts.kind === "line") {
        for (const s of d.series) {
          ctx.beginPath();
          ctx.arc(X(this.hover), Y(s.values[this.hover]), 4, 0, 2 * Math.PI);
          ctx.fillStyle = cssVar(s.color);
          ctx.strokeStyle = surface;
          ctx.lineWidth = 2;
          ctx.fill(); ctx.stroke();
        }
      }
    }
  }
}
