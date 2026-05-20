import {
  Application,
  Container,
  Graphics,
  Text,
  TextStyle,
  type FederatedPointerEvent,
} from 'pixi.js';

// ─── colour constants ────────────────────────────────────────────────────────

const SECTION_COLORS: Record<string, number> = {
  intro:     0x3b82f6,
  verse:     0x22c55e,
  chorus:    0xa855f7,
  drop:      0xa855f7,
  breakdown: 0xf97316,
  bridge:    0x14b8a6,
  build:     0xeab308,
  outro:     0xef4444,
};

const CUE_COLORS: Record<string, number> = {
  mix_in:    0x22c55e,
  mix_out:   0xf97316,
  drop:      0xfbbf24,
  vocal_in:  0x06b6d4,
  breakdown: 0xef4444,
  _default:  0xa855f7,
};

// ─── public types ───────────────────────────────────────────────────────────

export interface WaveformSection {
  label: string;
  start: number;
  end: number;
}

export interface WaveformCuePoint {
  label: string;
  time: number;
}

export interface WaveformData {
  /** [low, mid, high] peaks normalised 0-1, one entry per analysis frame */
  frames: number[][] | null;
  duration: number;
  beats: number[];
  downbeats: number[];
  /** phrase-boundary beat times */
  phrases: number[];
  sections: WaveformSection[];
  cuePoints: WaveformCuePoint[];
}

// ─── renderer ───────────────────────────────────────────────────────────────

export class WaveformRenderer {
  private app: Application | null = null;
  private ready = false;

  // layers (added to stage in z-order)
  private readonly layerSections  = new Container();
  private readonly layerWaveform  = new Container();
  private readonly layerBeats     = new Container();
  private readonly layerCues      = new Container();
  private readonly gCursor        = new Graphics();

  // graphics objects reused across redraws
  private readonly gSections    = new Graphics();
  private readonly labelSections = new Container();
  private readonly gLow        = new Graphics();
  private readonly gMid        = new Graphics();
  private readonly gHigh       = new Graphics();
  private readonly gBeats      = new Graphics();
  private readonly gDownbeats  = new Graphics();
  private readonly gPhrases    = new Graphics();

  // viewport
  private zoom = 1;   // 1 = full track fits in canvas width
  private pan  = 0;   // horizontal scroll in pixels

  // current dataset
  private data: WaveformData | null = null;

  // canvas size (CSS pixels)
  private w = 800;
  private h = 160;

  // drag state
  private dragging   = false;
  private dragStartX = 0;
  private dragPan    = 0;

  // seek callback (updated via ref, never goes stale)
  private onSeek: ((t: number) => void) = () => {};

  // ── lifecycle ─────────────────────────────────────────────────────────────

  async init(canvas: HTMLCanvasElement, onSeek: (t: number) => void): Promise<void> {
    this.onSeek = onSeek;
    this.w = canvas.getBoundingClientRect().width || 800;
    this.h = canvas.getBoundingClientRect().height || 160;

    this.app = new Application();
    await this.app.init({
      canvas,
      width:           this.w,
      height:          this.h,
      backgroundColor: 0x0d0d14,
      antialias:       false,
      resolution:      window.devicePixelRatio || 1,
      autoDensity:     true,
    });

    this.layerWaveform.addChild(this.gLow, this.gMid, this.gHigh);
    this.layerBeats.addChild(this.gBeats, this.gDownbeats, this.gPhrases);
    this.layerSections.addChild(this.gSections, this.labelSections);

    this.app.stage.addChild(
      this.layerSections,
      this.layerWaveform,
      this.layerBeats,
      this.layerCues,
      this.gCursor,
    );

    this.app.stage.eventMode = 'static';
    this.app.stage.hitArea   = this.app.screen;
    this.app.stage.on('pointerdown',  this.onDown);
    this.app.stage.on('pointermove',  this.onMove);
    this.app.stage.on('pointerup',    this.onUp);
    this.app.stage.on('pointerleave', this.onUp);
    canvas.addEventListener('wheel', this.onWheel, { passive: false });

    this.ready = true;
  }

  setOnSeek(fn: (t: number) => void): void {
    this.onSeek = fn;
  }

  destroy(): void {
    this.ready = false;
    const canvas = this.app?.canvas as HTMLCanvasElement | null;
    canvas?.removeEventListener('wheel', this.onWheel);
    this.app?.destroy(false);
    this.app = null;
  }

  // ── public update methods ─────────────────────────────────────────────────

  setData(data: WaveformData): void {
    if (!this.ready) return;
    this.data  = data;
    this.zoom  = 1;
    this.pan   = 0;
    this.redrawAll();
  }

  updateCursor(time: number): void {
    if (!this.ready || !this.data) return;
    const x = this.toX(time);
    this.gCursor.clear();
    if (x >= -1 && x <= this.w + 1) {
      this.gCursor
        .moveTo(x, 0)
        .lineTo(x, this.h)
        .stroke({ color: 0x00e5ff, width: 1.5, alpha: 0.9 });
    }
  }

  resize(w: number, h: number): void {
    if (!this.ready || !this.app) return;
    this.w = w;
    this.h = h;
    this.app.renderer.resize(w, h);
    this.app.stage.hitArea = this.app.screen;
    this.clampPan();
    this.redrawAll();
  }

  // ── coordinate helpers ────────────────────────────────────────────────────

  private totalW(): number {
    return this.w * this.zoom;
  }

  private toX(time: number): number {
    if (!this.data) return 0;
    return (time / this.data.duration) * this.totalW() - this.pan;
  }

  private toTime(x: number): number {
    if (!this.data) return 0;
    const t = ((x + this.pan) / this.totalW()) * this.data.duration;
    return Math.max(0, Math.min(this.data.duration, t));
  }

  private clampPan(): void {
    const maxPan = Math.max(0, this.totalW() - this.w);
    this.pan = Math.max(0, Math.min(maxPan, this.pan));
  }

  // ── draw ──────────────────────────────────────────────────────────────────

  private redrawAll(): void {
    this.drawSections();
    this.drawWaveform();
    this.drawBeats();
    this.drawCues();
  }

  private drawSections(): void {
    this.gSections.clear();
    if (!this.data) return;
    for (const sec of this.data.sections) {
      const x = this.toX(sec.start);
      const xe = this.toX(sec.end);
      if (xe < 0 || x > this.w) continue;
      const cx  = Math.max(0, x);
      const cw  = Math.min(xe, this.w) - cx;
      const col = SECTION_COLORS[sec.label.toLowerCase()] ?? 0x555566;
      this.gSections.rect(cx, 0, cw, this.h).fill({ color: col, alpha: 0.13 });
    }

    // Section labels — only shown at zoom >= 2 to avoid clutter
    for (const child of [...this.labelSections.children]) {
      child.destroy({ children: true });
    }
    this.labelSections.removeChildren();

    if (this.zoom < 2) return;
    for (const sec of this.data.sections) {
      const x = this.toX(sec.start);
      if (x < 0 || x > this.w - 4) continue;
      const col = SECTION_COLORS[sec.label.toLowerCase()] ?? 0x888888;
      const t = new Text({
        text: sec.label,
        style: new TextStyle({ fontSize: 9, fill: col, fontFamily: 'system-ui, sans-serif' }),
      });
      t.x = x + 3;
      t.y = 2;
      this.labelSections.addChild(t);
    }
  }

  private drawWaveform(): void {
    this.gLow.clear();
    this.gMid.clear();
    this.gHigh.clear();

    const cy = this.h / 2;
    const d  = this.data;

    if (!d || !d.frames || d.frames.length === 0) {
      this.gMid.rect(0, cy - 1, this.w, 2).fill({ color: 0x444466, alpha: 0.5 });
      return;
    }

    const frameDur = d.duration / d.frames.length;
    const startTime = this.toTime(0);
    const endTime   = this.toTime(this.w);
    const fi0 = Math.max(0, Math.floor(startTime / frameDur));
    const fi1 = Math.min(d.frames.length, Math.ceil(endTime / frameDur) + 1);

    for (let i = fi0; i < fi1; i++) {
      const frame = d.frames[i];
      const low   = frame[0] ?? 0;
      const mid   = frame[1] ?? 0;
      const high  = frame[2] ?? 0;
      const x     = this.toX(i * frameDur);
      const xn    = this.toX((i + 1) * frameDur);
      const bw    = Math.max(1, xn - x);

      if (low  > 0.005) this.gLow .rect(x, cy - low  * cy,        bw, low  * cy * 2);
      if (mid  > 0.005) this.gMid .rect(x, cy - mid  * cy * 0.75, bw, mid  * cy * 1.5);
      if (high > 0.005) this.gHigh.rect(x, cy - high * cy * 0.5,  bw, high * cy);
    }

    this.gLow .fill({ color: 0xff3333, alpha: 0.80 });
    this.gMid .fill({ color: 0x44ff88, alpha: 0.55 });
    this.gHigh.fill({ color: 0x3388ff, alpha: 0.45 });
  }

  private drawBeats(): void {
    this.gBeats.clear();
    this.gDownbeats.clear();
    this.gPhrases.clear();
    const d = this.data;
    if (!d || d.beats.length === 0) return;

    const phraseSet   = new Set(d.phrases);
    const downbeatSet = new Set(d.downbeats);

    for (const b of d.beats) {
      const x = this.toX(b);
      if (x < 0 || x > this.w) continue;

      if (phraseSet.has(b)) {
        this.gPhrases.moveTo(x, 0).lineTo(x, this.h);
      } else if (downbeatSet.has(b)) {
        this.gDownbeats.moveTo(x, 0).lineTo(x, this.h);
      } else {
        this.gBeats.moveTo(x, this.h * 0.2).lineTo(x, this.h * 0.8);
      }
    }

    this.gBeats.stroke    ({ color: 0xffffff, width: 0.5, alpha: 0.15 });
    this.gDownbeats.stroke({ color: 0xffffff, width: 1.0, alpha: 0.35 });
    this.gPhrases.stroke  ({ color: 0xffffff, width: 2.0, alpha: 0.60 });
  }

  private drawCues(): void {
    for (const child of [...this.layerCues.children]) {
      child.destroy({ children: true });
    }
    this.layerCues.removeChildren();
    const d = this.data;
    if (!d) return;

    for (const cue of d.cuePoints) {
      const x = this.toX(cue.time);
      if (x < -20 || x > this.w + 20) continue;

      const col = CUE_COLORS[cue.label] ?? CUE_COLORS['_default'];
      const g   = new Graphics();

      // vertical line
      g.moveTo(x, 0).lineTo(x, this.h).stroke({ color: col, width: 1.5, alpha: 0.85 });

      // small downward triangle at top edge
      g.moveTo(x - 5, 0).lineTo(x + 5, 0).lineTo(x, 9).closePath().fill(col);

      // label
      const label = new Text({
        text: cue.label.replace(/_/g, ' '),
        style: new TextStyle({
          fontSize:   9,
          fill:       col,
          fontFamily: 'system-ui, sans-serif',
        }),
      });
      label.x = x + 4;
      label.y = 10;

      const group = new Container();
      group.addChild(g, label);
      this.layerCues.addChild(group);
    }
  }

  // ── events ────────────────────────────────────────────────────────────────

  private onDown = (e: FederatedPointerEvent) => {
    this.dragging   = false;
    this.dragStartX = e.globalX;
    this.dragPan    = this.pan;
  };

  private onMove = (e: FederatedPointerEvent) => {
    if (e.buttons === 0) return;
    const dx = e.globalX - this.dragStartX;
    if (!this.dragging && Math.abs(dx) > 4) this.dragging = true;
    if (!this.dragging) return;
    this.pan = this.dragPan - dx;
    this.clampPan();
    this.redrawAll();
  };

  private onUp = (e: FederatedPointerEvent) => {
    if (!this.dragging && this.data) {
      this.onSeek(this.toTime(e.globalX));
    }
    this.dragging = false;
  };

  private onWheel = (e: WheelEvent) => {
    e.preventDefault();
    if (!this.data) return;

    const factor    = e.deltaY < 0 ? 1.18 : 1 / 1.18;
    const mouseX    = e.offsetX;
    const timeBefore = this.toTime(mouseX);

    this.zoom = Math.max(1, Math.min(32, this.zoom * factor));
    // keep the point under the cursor stationary
    const newX = this.toX(timeBefore);
    this.pan += newX - mouseX;
    this.clampPan();
    this.redrawAll();
  };
}
