"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { toPng } from "html-to-image";

// ─── Canvas dimensions (design at largest Apple size) ───────────────────────
const W = 1320;
const H = 2868;

const SIZES = [
  { label: '6.9"', w: 1320, h: 2868 },
  { label: '6.5"', w: 1284, h: 2778 },
  { label: '6.3"', w: 1206, h: 2622 },
  { label: '6.1"', w: 1125, h: 2436 },
] as const;

// ─── Phone mockup measurements ───────────────────────────────────────────────
const MK_W = 1022;
const MK_H = 2082;
const SC_L = (52 / MK_W) * 100;
const SC_T = (46 / MK_H) * 100;
const SC_W = (918 / MK_W) * 100;
const SC_H = (1990 / MK_H) * 100;
const SC_RX = (126 / 918) * 100;
const SC_RY = (126 / 1990) * 100;

// ─── Brand ───────────────────────────────────────────────────────────────────
const ORANGE = "#E8601C";
const ORANGE_LIGHT = "#FF7A35";
const ORANGE_DIM = "rgba(232,96,28,0.18)";
const BG_DARK = "#0A0A0A";
const BG_CARD = "#141414";

// ─── Phone component ─────────────────────────────────────────────────────────
function Phone({
  src,
  alt,
  style,
  className = "",
}: {
  src: string;
  alt: string;
  style?: React.CSSProperties;
  className?: string;
}) {
  return (
    <div
      className={`relative ${className}`}
      style={{ aspectRatio: `${MK_W}/${MK_H}`, ...style }}
    >
      <img src="/mockup.png" alt="" className="block w-full h-full" draggable={false} />
      <div
        className="absolute z-10 overflow-hidden"
        style={{
          left: `${SC_L}%`,
          top: `${SC_T}%`,
          width: `${SC_W}%`,
          height: `${SC_H}%`,
          borderRadius: `${SC_RX}% / ${SC_RY}%`,
        }}
      >
        <img
          src={src}
          alt={alt}
          className="block w-full h-full object-cover object-top"
          draggable={false}
        />
      </div>
    </div>
  );
}

// ─── Shared caption ───────────────────────────────────────────────────────────
function Caption({
  label,
  headline,
  light = false,
}: {
  label: string;
  headline: React.ReactNode;
  light?: boolean;
}) {
  return (
    <div style={{ textAlign: "center" }}>
      <div
        style={{
          fontSize: W * 0.028,
          fontWeight: 700,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: ORANGE,
          marginBottom: W * 0.016,
          fontFamily: "inherit",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: W * 0.092,
          fontWeight: 900,
          lineHeight: 0.95,
          color: light ? BG_DARK : "#FFFFFF",
          fontFamily: "inherit",
          letterSpacing: "-0.02em",
        }}
      >
        {headline}
      </div>
    </div>
  );
}

// ─── Glow blob ────────────────────────────────────────────────────────────────
function Glow({
  x,
  y,
  size,
  opacity = 0.35,
  color = ORANGE,
}: {
  x: number;
  y: number;
  size: number;
  opacity?: number;
  color?: string;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: color,
        opacity,
        filter: `blur(${size * 0.38}px)`,
        pointerEvents: "none",
      }}
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 1 — Hero: "Your personal shot doctor."
// ─────────────────────────────────────────────────────────────────────────────
function Slide1() {
  return (
    <div
      style={{
        width: W,
        height: H,
        background: BG_DARK,
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
      }}
    >
      {/* Warm orange glow top-center */}
      <Glow x={W * 0.5} y={H * 0.22} size={W * 1.1} opacity={0.26} />
      <Glow x={W * 0.5} y={H * 0.17} size={W * 0.55} opacity={0.2} />

      {/* Logo + name + headline all stacked top */}
      <div
        style={{
          position: "absolute",
          top: H * 0.07,
          left: 0,
          right: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: W * 0.024,
        }}
      >
        <img
          src="/logo-transparent.png"
          alt="ShotDoc logo"
          style={{ width: W * 0.22, height: "auto" }}
          draggable={false}
        />
        <div
          style={{
            fontSize: W * 0.065,
            fontWeight: 900,
            color: "#FFFFFF",
            letterSpacing: "-0.02em",
            fontFamily: "inherit",
          }}
        >
          ShotDoc
        </div>
        <div style={{ height: W * 0.01 }} />
        <div
          style={{
            fontSize: W * 0.028,
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: ORANGE,
            fontFamily: "inherit",
          }}
        >
          AI Basketball Coach
        </div>
        <div
          style={{
            fontSize: W * 0.094,
            fontWeight: 900,
            lineHeight: 0.92,
            color: "#FFFFFF",
            fontFamily: "inherit",
            letterSpacing: "-0.025em",
            textAlign: "center",
          }}
        >
          Your personal
          <br />
          shot doctor.
        </div>
      </div>

      {/* Phone centered at bottom */}
      <Phone
        src="/screenshots/home.png"
        alt="Home screen"
        style={{
          position: "absolute",
          width: W * 0.82,
          bottom: 0,
          left: "50%",
          transform: "translateX(-50%) translateY(6%)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 2 — Shot analysis: "Fix one thing. Every shot."
// ─────────────────────────────────────────────────────────────────────────────
function Slide2() {
  return (
    <div
      style={{
        width: W,
        height: H,
        background: `radial-gradient(ellipse 120% 60% at 80% 30%, rgba(232,96,28,0.22) 0%, ${BG_DARK} 65%)`,
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
      }}
    >
      <Glow x={W * 0.85} y={H * 0.25} size={W * 0.7} opacity={0.25} />

      {/* Caption top */}
      <div
        style={{
          position: "absolute",
          top: H * 0.07,
          left: W * 0.08,
          right: W * 0.08,
        }}
      >
        <Caption label="Shot Analysis" headline={<>Know exactly<br />what to fix.</>} />
      </div>

      {/* Phone right-weighted */}
      <Phone
        src="/screenshots/shot-detail.png"
        alt="Shot detail"
        style={{
          position: "absolute",
          width: W * 0.82,
          bottom: 0,
          right: "-4%",
          transform: "translateY(10%)",
        }}
      />

      {/* Stat callout floating left */}
      <div
        style={{
          position: "absolute",
          left: W * 0.06,
          bottom: H * 0.28,
          background: BG_CARD,
          border: `1.5px solid ${ORANGE_DIM}`,
          borderRadius: W * 0.04,
          padding: `${W * 0.04}px ${W * 0.05}px`,
          minWidth: W * 0.3,
        }}
      >
        <div style={{ fontSize: W * 0.026, color: "#888", fontWeight: 600, marginBottom: 8, fontFamily: "inherit", letterSpacing: "0.06em", textTransform: "uppercase" }}>Quick Cue</div>
        <div style={{ fontSize: W * 0.046, fontWeight: 800, color: "#FFFFFF", fontFamily: "inherit", lineHeight: 1.1 }}>"Widen<br />your stance"</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 3 — Real-time tracking: "Every shot, tracked."  (LIGHT contrast slide)
// ─────────────────────────────────────────────────────────────────────────────
function Slide3() {
  return (
    <div
      style={{
        width: W,
        height: H,
        background: "#F5F0EB",
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
      }}
    >
      {/* Warm glow top right */}
      <Glow x={W * 0.9} y={H * 0.08} size={W * 0.7} opacity={0.18} color={ORANGE} />

      {/* Caption */}
      <div
        style={{
          position: "absolute",
          top: H * 0.07,
          left: W * 0.08,
          right: W * 0.08,
        }}
      >
        <Caption label="Live Session" headline={<>Every shot,<br />tracked.</>} light />
      </div>

      {/* Phone centered */}
      <Phone
        src="/screenshots/session.png"
        alt="Session tracking"
        style={{
          position: "absolute",
          width: W * 0.82,
          bottom: 0,
          left: "50%",
          transform: "translateX(-50%) translateY(12%)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 4 — Progress: "See how far you've come."
// ─────────────────────────────────────────────────────────────────────────────
function Slide4() {
  return (
    <div
      style={{
        width: W,
        height: H,
        background: `radial-gradient(ellipse 100% 50% at 20% 70%, rgba(232,96,28,0.2) 0%, ${BG_DARK} 60%)`,
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
      }}
    >
      <Glow x={W * 0.15} y={H * 0.72} size={W * 0.65} opacity={0.22} />

      {/* Caption */}
      <div
        style={{
          position: "absolute",
          top: H * 0.07,
          left: W * 0.08,
          right: W * 0.08,
        }}
      >
        <Caption label="Track Progress" headline={<>See how far<br />you've come.</>} />
      </div>

      {/* Two phones layered */}
      {/* Back phone */}
      <Phone
        src="/screenshots/results.png"
        alt="Results"
        style={{
          position: "absolute",
          width: W * 0.65,
          bottom: 0,
          left: "-6%",
          transform: "rotate(-5deg) translateY(14%)",
          opacity: 0.55,
        }}
      />
      {/* Front phone */}
      <Phone
        src="/screenshots/history.png"
        alt="History"
        style={{
          position: "absolute",
          width: W * 0.82,
          bottom: 0,
          right: "-2%",
          transform: "translateY(10%)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 5 — Identity: "Built for hoopers who study the game."
// ─────────────────────────────────────────────────────────────────────────────
function Slide5() {
  return (
    <div
      style={{
        width: W,
        height: H,
        background: `radial-gradient(ellipse 110% 55% at 50% 75%, rgba(232,96,28,0.2) 0%, ${BG_DARK} 60%)`,
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
      }}
    >
      <Glow x={W * 0.5} y={H * 0.72} size={W * 0.9} opacity={0.2} />

      {/* Caption top */}
      <div
        style={{
          position: "absolute",
          top: H * 0.07,
          left: W * 0.08,
          right: W * 0.08,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: W * 0.028,
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: ORANGE,
            marginBottom: W * 0.016,
            fontFamily: "inherit",
          }}
        >
          For Serious Hoopers
        </div>
        <div
          style={{
            fontSize: W * 0.094,
            fontWeight: 900,
            lineHeight: 0.93,
            color: "#FFFFFF",
            fontFamily: "inherit",
            letterSpacing: "-0.025em",
          }}
        >
          Built for hoopers
          <br />
          <span style={{ color: ORANGE_LIGHT }}>who study</span>
          <br />
          the game.
        </div>
      </div>

      {/* Phone centered */}
      <Phone
        src="/screenshots/shot-detail.png"
        alt="Shot analysis detail"
        style={{
          position: "absolute",
          width: W * 0.8,
          bottom: 0,
          left: "50%",
          transform: "translateX(-50%) translateY(10%)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 6 — More features
// ─────────────────────────────────────────────────────────────────────────────
function Slide6() {
  const features = [
    "AI Form Analysis",
    "Make/Miss Tracking",
    "Session History",
    "Quick Coaching Cues",
    "Elbow Angle Detection",
    "Knee Bend Analysis",
    "Wrist Release Tracking",
    "Drill Recommendations",
    "Shooting % Trends",
  ];
  const soon = ["Fingerprint Charts", "Video Export", "Live Coaching"];

  return (
    <div
      style={{
        width: W,
        height: H,
        background: BG_DARK,
        position: "relative",
        overflow: "hidden",
        fontFamily: "inherit",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: H * 0.042,
        padding: `0 ${W * 0.1}px`,
      }}
    >
      <Glow x={W * 0.5} y={H * 0.18} size={W * 0.9} opacity={0.18} />
      <Glow x={W * 0.5} y={H * 0.85} size={W * 0.7} opacity={0.12} />

      <img src="/logo-transparent.png" alt="ShotDoc" style={{ width: W * 0.18, height: "auto" }} draggable={false} />

      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: W * 0.028, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: ORANGE, marginBottom: W * 0.016, fontFamily: "inherit" }}>
          Everything You Need
        </div>
        <div style={{ fontSize: W * 0.088, fontWeight: 900, lineHeight: 0.93, color: "#FFFFFF", fontFamily: "inherit", letterSpacing: "-0.025em" }}>
          And so much
          <br />more.
        </div>
      </div>

      {/* Feature pills */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: W * 0.022, justifyContent: "center", maxWidth: W * 0.88 }}>
        {features.map((f, i) => (
          <div
            key={i}
            style={{
              background: BG_CARD,
              border: `1.5px solid rgba(232,96,28,0.25)`,
              borderRadius: W * 0.08,
              padding: `${W * 0.022}px ${W * 0.038}px`,
              fontSize: W * 0.032,
              fontWeight: 600,
              color: "#FFFFFF",
              fontFamily: "inherit",
            }}
          >
            {f}
          </div>
        ))}
      </div>

      {/* Coming soon */}
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: W * 0.024, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#555", marginBottom: W * 0.018, fontFamily: "inherit" }}>
          Coming Soon
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: W * 0.018, justifyContent: "center" }}>
          {soon.map((f, i) => (
            <div
              key={i}
              style={{
                background: "transparent",
                border: `1.5px solid #333`,
                borderRadius: W * 0.08,
                padding: `${W * 0.02}px ${W * 0.036}px`,
                fontSize: W * 0.03,
                fontWeight: 600,
                color: "#555",
                fontFamily: "inherit",
              }}
            >
              {f}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Slides registry ──────────────────────────────────────────────────────────
const SLIDES = [
  { id: "hero",     label: "01 · Hero",          Component: Slide1 },
  { id: "analysis", label: "02 · Shot Analysis", Component: Slide2 },
  { id: "tracking", label: "03 · Tracking",      Component: Slide3 },
  { id: "progress", label: "04 · Progress",      Component: Slide4 },
  { id: "identity", label: "05 · Identity",      Component: Slide5 },
  { id: "more",     label: "06 · More",          Component: Slide6 },
];

// ─── Preview card ─────────────────────────────────────────────────────────────
function ScreenshotPreview({
  slide,
  index,
  onExport,
  exporting,
}: {
  slide: (typeof SLIDES)[number];
  index: number;
  onExport: (index: number) => void;
  exporting: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      const cw = containerRef.current.clientWidth;
      setScale(cw / W);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const { Component } = slide;

  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm font-semibold text-zinc-400 tracking-wide">{slide.label}</div>
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-2xl shadow-2xl cursor-pointer hover:ring-2 hover:ring-orange-500 transition-all"
        style={{ width: "100%", aspectRatio: `${W}/${H}` }}
        onClick={() => onExport(index)}
      >
        <div
          ref={innerRef}
          style={{
            width: W,
            height: H,
            transform: `scale(${scale})`,
            transformOrigin: "top left",
          }}
        >
          <Component />
        </div>
        {exporting && (
          <div className="absolute inset-0 bg-black/60 flex items-center justify-center rounded-2xl">
            <div className="text-white text-sm font-semibold animate-pulse">Exporting…</div>
          </div>
        )}
      </div>
      <button
        onClick={() => onExport(index)}
        disabled={exporting}
        className="text-xs font-semibold text-orange-400 hover:text-orange-300 transition-colors disabled:opacity-40 text-center"
      >
        Export this slide ↓
      </button>
    </div>
  );
}

// ─── Offscreen export container ──────────────────────────────────────────────
function OffscreenSlides({ refs }: { refs: React.MutableRefObject<(HTMLDivElement | null)[]> }) {
  return (
    <div style={{ position: "absolute", left: -9999, top: 0, opacity: 0 }}>
      {SLIDES.map(({ Component }, i) => (
        <div
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          style={{ width: W, height: H, fontFamily: "'Barlow', sans-serif" }}
        >
          <Component />
        </div>
      ))}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ScreenshotsPage() {
  const offscreenRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [exportingIdx, setExportingIdx] = useState<number | null>(null);
  const [exportingAll, setExportingAll] = useState(false);
  const [selectedSize, setSelectedSize] = useState<(typeof SIZES)[number]>(SIZES[0]);

  const exportSlide = useCallback(
    async (index: number, sizeOverride?: (typeof SIZES)[number]) => {
      const el = offscreenRefs.current[index];
      if (!el) return;
      const size = sizeOverride ?? selectedSize;

      el.style.left = "0px";
      el.style.opacity = "1";
      el.style.zIndex = "-1";

      const opts = { width: W, height: H, pixelRatio: 1, cacheBust: true };
      try {
        await toPng(el, opts); // warm-up
        const dataUrl = await toPng(el, opts);

        // Resize to target size
        const img = new Image();
        img.src = dataUrl;
        await new Promise((r) => (img.onload = r));
        const canvas = document.createElement("canvas");
        canvas.width = size.w;
        canvas.height = size.h;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, size.w, size.h);

        const a = document.createElement("a");
        const idx = String(index + 1).padStart(2, "0");
        a.download = `${idx}-${SLIDES[index].id}-${size.w}x${size.h}.png`;
        a.href = canvas.toDataURL("image/png");
        a.click();
      } finally {
        el.style.left = "-9999px";
        el.style.opacity = "";
        el.style.zIndex = "";
      }
    },
    [selectedSize]
  );

  const handleExportOne = useCallback(
    async (index: number) => {
      setExportingIdx(index);
      await exportSlide(index);
      setExportingIdx(null);
    },
    [exportSlide]
  );

  const handleExportAll = useCallback(async () => {
    setExportingAll(true);
    for (let i = 0; i < SLIDES.length; i++) {
      setExportingIdx(i);
      await exportSlide(i);
      await new Promise((r) => setTimeout(r, 300));
    }
    setExportingIdx(null);
    setExportingAll(false);
  }, [exportSlide]);

  return (
    <>
      <OffscreenSlides refs={offscreenRefs} />
      <div className="min-h-screen bg-zinc-950 text-white p-8">
        {/* Header */}
        <div className="max-w-7xl mx-auto mb-10 flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-black tracking-tight">ShotDoc · App Store Screenshots</h1>
            <p className="text-zinc-500 text-sm mt-1">Click any slide to export. Hover for options.</p>
          </div>
          <div className="flex items-center gap-4">
            {/* Size picker */}
            <select
              value={selectedSize.label}
              onChange={(e) => setSelectedSize(SIZES.find((s) => s.label === e.target.value)!)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              {SIZES.map((s) => (
                <option key={s.label} value={s.label}>
                  {s.label} — {s.w}×{s.h}
                </option>
              ))}
            </select>
            <button
              onClick={handleExportAll}
              disabled={exportingAll}
              className="bg-orange-500 hover:bg-orange-400 disabled:opacity-50 text-white font-bold px-6 py-2 rounded-lg text-sm transition-colors"
            >
              {exportingAll ? `Exporting ${(exportingIdx ?? 0) + 1}/${SLIDES.length}…` : "Export All"}
            </button>
          </div>
        </div>

        {/* Grid */}
        <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-3 gap-8">
          {SLIDES.map((slide, i) => (
            <ScreenshotPreview
              key={slide.id}
              slide={slide}
              index={i}
              onExport={handleExportOne}
              exporting={exportingIdx === i}
            />
          ))}
        </div>
      </div>
    </>
  );
}
