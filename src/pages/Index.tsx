/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback } from "react";
import Icon from "@/components/ui/icon";

const API_MARKET = "https://functions.poehali.dev/b4830b16-e61f-4ab5-8a8b-eb323709567c";
const API_SIGNALS = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed";
const API_TRADE = "https://functions.poehali.dev/228287c1-2207-42c1-94aa-88fda52f4f86";

// ─── Types ────────────────────────────────────────────────────────────────────

interface PairData {
  symbol: string;
  raw: string;
  price: number;
  change: number;
  volume: number;
  high: number;
  low: number;
  rsi: number;
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
}

interface SignalData {
  pair: string;
  type: "LONG" | "SHORT";
  exchange: string;
  entry: number;
  target: number;
  stop: number;
  confidence: number;
  status: string;
  rsi: number;
  rsi_4h: number;
  macd: { macd: number; signal: number; hist: number; trend: string };
  bollinger: { upper: number; middle: number; lower: number; pct_b: number; squeeze: boolean };
  trend: { trend: string; strength: number };
  volume: { ratio: number; trend: string };
  fear_greed: { value: number; classification: string };
  divergence: string;
  factors: string[];
  analysis: string;
  risk_reward: number;
  potential_pct: number;
  time: string;
}

interface MarketState {
  pairs: PairData[];
  updatedAt: string;
  loading: boolean;
}

interface SignalsState {
  signals: SignalData[];
  fearGreed: { value: number; classification: string };
  loading: boolean;
  generatedAt: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtPrice(p: number): string {
  if (p >= 10000) return p.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
  if (p >= 100) return p.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(6);
}

function fmtVolume(v: number): string {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function fgColor(val: number): string {
  if (val <= 25) return "hsl(0 72% 51%)";
  if (val <= 45) return "hsl(25 95% 55%)";
  if (val <= 55) return "hsl(43 96% 56%)";
  if (val <= 75) return "hsl(158 64% 48%)";
  return "hsl(158 80% 40%)";
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return isMobile;
}

// ─── Candle Chart ─────────────────────────────────────────────────────────────

function CandleChart({ candles }: { candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[] }) {
  if (!candles || candles.length === 0) {
    return <div className="flex items-center justify-center h-full text-muted-foreground text-xs">Загрузка графика...</div>;
  }
  const W = 900, H = 200;
  const pad = { top: 12, bottom: 24, left: 4, right: 64 };
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;
  const allPrices = candles.flatMap(c => [c.high, c.low]);
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const range = maxP - minP || 1;
  const toY = (p: number) => pad.top + chartH - ((p - minP) / range) * chartH;
  const candleW = chartW / candles.length;
  const maxVol = Math.max(...candles.map(c => c.volume));
  const labels = Array.from({ length: 5 }, (_, i) => ({ price: minP + (range / 4) * i, y: toY(minP + (range / 4) * i) }));

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
      {labels.map((l, i) => (
        <g key={i}>
          <line x1={pad.left} y1={l.y} x2={W - pad.right} y2={l.y} stroke="hsl(220 13% 13%)" strokeWidth="1" strokeDasharray="3,6" />
          <text x={W - pad.right + 4} y={l.y + 3.5} fill="hsl(215 12% 40%)" fontSize="9" fontFamily="IBM Plex Mono">
            {l.price >= 1000 ? `${(l.price / 1000).toFixed(1)}k` : l.price.toFixed(l.price < 1 ? 4 : 2)}
          </text>
        </g>
      ))}
      {candles.map((c, i) => {
        const x = pad.left + i * candleW + candleW * 0.15;
        const w = Math.max(candleW * 0.7, 1);
        const isUp = c.close >= c.open;
        const color = isUp ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)";
        const bodyTop = toY(Math.max(c.open, c.close));
        const bodyH = Math.max(Math.abs(toY(c.open) - toY(c.close)), 1);
        const cx = x + w / 2;
        const volH = (c.volume / (maxVol || 1)) * 20;
        return (
          <g key={i}>
            <rect x={x} y={H - pad.bottom - volH} width={w} height={volH} fill={color} opacity="0.2" />
            <line x1={cx} y1={toY(c.high)} x2={cx} y2={toY(c.low)} stroke={color} strokeWidth="1" opacity="0.75" />
            <rect x={x} y={bodyTop} width={w} height={bodyH} fill={color} opacity="0.9" />
          </g>
        );
      })}
    </svg>
  );
}

function Sparkline({ candles, positive }: { candles?: { close: number }[]; positive: boolean }) {
  const pts = candles && candles.length > 3
    ? candles.slice(-20).map(c => c.close)
    : Array.from({ length: 20 }, (_, i) => (positive ? 10 + i * 1.2 : 36 - i * 1.2) + (Math.random() - 0.5) * 6);
  const min = Math.min(...pts), max = Math.max(...pts);
  const norm = pts.map(p => ((p - min) / (max - min || 1)) * 26 + 4);
  const path = norm.map((y, i) => `${(i / (norm.length - 1)) * 72},${34 - y}`).join(" ");
  return (
    <svg width="52" height="26" viewBox="0 0 72 34">
      <polyline points={path} fill="none" stroke={positive ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)"} strokeWidth="1.5" opacity="0.8" />
    </svg>
  );
}

// ─── Fear & Greed Gauge ───────────────────────────────────────────────────────

function FearGreedGauge({ value }: { value: number }) {
  const angle = -135 + (value / 100) * 270;
  const color = fgColor(value);
  const cx = 50, cy = 54, r = 38;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const needleX = cx + (r - 8) * Math.cos(toRad(angle));
  const needleY = cy + (r - 8) * Math.sin(toRad(angle));
  const arcPath = (s: number, e: number) => {
    const [x1, y1] = [cx + r * Math.cos(toRad(s)), cy + r * Math.sin(toRad(s))];
    const [x2, y2] = [cx + r * Math.cos(toRad(e)), cy + r * Math.sin(toRad(e))];
    return `M ${x1} ${y1} A ${r} ${r} 0 ${e - s > 180 ? 1 : 0} 1 ${x2} ${y2}`;
  };
  return (
    <svg width="90" height="56" viewBox="0 0 100 60">
      {[[-135, -81, "hsl(0 72% 51%)"], [-81, -27, "hsl(25 95% 55%)"], [-27, 27, "hsl(43 96% 56%)"], [27, 81, "hsl(100 60% 50%)"], [81, 135, "hsl(158 64% 48%)"]].map(([s, e, c], i) => (
        <path key={i} d={arcPath(s as number, e as number)} fill="none" stroke={c as string} strokeWidth="6" opacity="0.7" />
      ))}
      <line x1={cx} y1={cy} x2={needleX} y2={needleY} stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="3" fill={color} />
      <text x={cx} y={cy - 10} textAnchor="middle" fill={color} fontSize="11" fontFamily="IBM Plex Mono" fontWeight="600">{value}</text>
    </svg>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ market, signals }: { market: MarketState; signals: SignalsState }) {
  const [selectedPair, setSelectedPair] = useState(0);
  const isMobile = useIsMobile();
  const btc = market.pairs[0];
  const activePair = market.pairs[selectedPair] || market.pairs[0];
  const longs = signals.signals.filter(s => s.type === "LONG").length;
  const shorts = signals.signals.filter(s => s.type === "SHORT").length;

  return (
    <div className="flex flex-col gap-3 fade-in">
      {/* Metrics — 2 cols mobile, 4 cols desktop */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3">
        <div className="panel rounded p-3 md:p-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-muted-foreground text-xs uppercase tracking-wider">BTC/USDT</span>
            <Icon name="Bitcoin" size={12} className="text-muted-foreground" />
          </div>
          <div className="font-mono text-base md:text-xl font-semibold" style={{ color: btc ? (btc.change >= 0 ? "hsl(var(--bull))" : "hsl(var(--bear))") : "hsl(var(--foreground))" }}>
            {btc ? `$${fmtPrice(btc.price)}` : "..."}
          </div>
          <div className={`text-xs mt-1 font-mono ${btc && btc.change >= 0 ? "bull" : "bear"}`}>
            {btc ? `${btc.change >= 0 ? "+" : ""}${btc.change.toFixed(2)}%` : "загрузка..."}
          </div>
        </div>
        <div className="panel rounded p-3 md:p-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-muted-foreground text-xs uppercase tracking-wider">Fear & Greed</span>
            <Icon name="Activity" size={12} className="text-muted-foreground" />
          </div>
          {signals.loading ? <div className="font-mono text-base text-muted-foreground">...</div> : (
            <>
              <FearGreedGauge value={signals.fearGreed.value} />
              <div className="text-xs font-mono" style={{ color: fgColor(signals.fearGreed.value) }}>{signals.fearGreed.classification}</div>
            </>
          )}
        </div>
        <div className="panel rounded p-3 md:p-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-muted-foreground text-xs uppercase tracking-wider">AI Сигналы</span>
            <Icon name="Zap" size={12} className="text-muted-foreground" />
          </div>
          <div className="font-mono text-base md:text-xl font-semibold">{signals.loading ? "..." : signals.signals.length}</div>
          <div className="text-xs text-muted-foreground mt-1">
            <span className="bull">{longs} LONG</span> · <span className="bear">{shorts} SHORT</span>
          </div>
        </div>
        <div className="panel rounded p-3 md:p-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-muted-foreground text-xs uppercase tracking-wider">Портфель</span>
            <Icon name="Wallet" size={12} className="text-muted-foreground" />
          </div>
          <div className="font-mono text-base md:text-xl font-semibold bull">$1,000</div>
          <div className="text-xs text-muted-foreground mt-1 font-mono">
            25 пар · порог 90%+
          </div>
        </div>
      </div>

      {/* Chart + Pairs — stacked on mobile, side-by-side on desktop */}
      <div className="flex flex-col md:grid md:grid-cols-3 gap-3" style={isMobile ? {} : { minHeight: 0, flex: "1 1 0" }}>
        <div className="md:col-span-2 panel rounded flex flex-col">
          <div className="flex flex-wrap items-center justify-between gap-1 px-3 md:px-4 py-2 border-b border-border">
            <div className="flex items-center gap-2 md:gap-3">
              <span className="font-mono font-semibold text-xs md:text-sm">{activePair?.symbol || "BTC/USDT"}</span>
              <span className={`font-mono text-sm md:text-base ${activePair && activePair.change >= 0 ? "bull" : "bear"}`}>
                {activePair ? fmtPrice(activePair.price) : "—"}
              </span>
              {activePair && (
                <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${activePair.change >= 0 ? "badge-bull" : "badge-bear"}`}>
                  {activePair.change >= 0 ? "+" : ""}{activePair.change.toFixed(2)}%
                </span>
              )}
            </div>
            {activePair && !isMobile && (
              <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
                <span>H: <span className="text-foreground">{fmtPrice(activePair.high)}</span></span>
                <span>L: <span className="text-foreground">{fmtPrice(activePair.low)}</span></span>
                <span>Vol: <span className="text-foreground">{fmtVolume(activePair.volume)}</span></span>
                <span>RSI: <span className={activePair.rsi > 70 ? "bear" : activePair.rsi < 30 ? "bull" : "text-foreground"}>{activePair.rsi}</span></span>
              </div>
            )}
            {activePair && isMobile && (
              <div className="flex gap-3 text-xs font-mono text-muted-foreground">
                <span>RSI: <span className={activePair.rsi > 70 ? "bear" : activePair.rsi < 30 ? "bull" : "text-foreground"}>{activePair.rsi}</span></span>
                <span>Vol: <span className="text-foreground">{fmtVolume(activePair.volume)}</span></span>
              </div>
            )}
          </div>
          <div className="p-2" style={{ height: isMobile ? "140px" : "200px" }}>
            {market.loading ? (
              <div className="flex items-center justify-center h-full gap-2">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-muted-foreground font-mono">Загрузка с Binance...</span>
              </div>
            ) : <CandleChart candles={activePair?.candles || []} />}
          </div>
        </div>

        {/* Market Pairs */}
        <div className="panel rounded flex flex-col" style={{ maxHeight: isMobile ? "280px" : undefined }}>
          <div className="px-3 md:px-4 py-2 border-b border-border flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Рынок</span>
            {market.loading && <div className="w-3 h-3 border border-primary border-t-transparent rounded-full animate-spin" />}
          </div>
          <div className="overflow-y-auto flex-1">
            {(market.loading ? Array(6).fill(null) : market.pairs).map((p, i) => (
              <div key={i} onClick={() => p && setSelectedPair(i)}
                className={`flex items-center justify-between px-3 md:px-4 py-2 row-hover border-b border-border/40 cursor-pointer ${selectedPair === i ? "bg-accent" : ""}`}>
                {!p ? (
                  <div className="flex items-center gap-2 w-full">
                    <div className="w-12 h-5 bg-secondary rounded animate-pulse" />
                    <div className="flex-1"><div className="w-16 h-2.5 bg-secondary rounded animate-pulse mb-1" /><div className="w-10 h-2 bg-secondary rounded animate-pulse" /></div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      <Sparkline candles={p.candles} positive={p.change >= 0} />
                      <div>
                        <div className="font-mono text-xs font-medium">{p.symbol}</div>
                        <div className="text-muted-foreground text-xs font-mono">{fmtVolume(p.volume)}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-xs">{fmtPrice(p.price)}</div>
                      <div className={`font-mono text-xs ${p.change >= 0 ? "bull" : "bear"}`}>{p.change >= 0 ? "+" : ""}{p.change.toFixed(2)}%</div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Status Bar */}
      <div className="panel rounded p-2 md:p-2.5 flex flex-wrap items-center gap-3 md:gap-6">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">Статус:</span>
        {["Binance API", "AI Engine", "Fear & Greed"].map((e, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full blink ${market.loading && i === 0 ? "bg-gold" : "bg-bull"}`} />
            <span className="font-mono text-xs">{e}</span>
          </div>
        ))}
        <div className="ml-auto font-mono text-xs text-muted-foreground">{new Date().toLocaleTimeString("ru-RU")}</div>
      </div>
    </div>
  );
}

// ─── Signals ──────────────────────────────────────────────────────────────────

function Signals({ signals }: { signals: SignalsState }) {
  const [filter, setFilter] = useState("Все");
  const [expanded, setExpanded] = useState<number | null>(null);
  const isMobile = useIsMobile();

  const filtered = signals.signals.filter(s => {
    if (filter === "LONG") return s.type === "LONG";
    if (filter === "SHORT") return s.type === "SHORT";
    if (filter === "Активные") return s.status === "active";
    return true;
  });

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold">AI Сигналы</span>
          {signals.loading
            ? <span className="badge-gold text-xs px-2 py-0.5 rounded-full font-mono flex items-center gap-1.5"><div className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />анализ...</span>
            : <span className="badge-bull text-xs px-2 py-0.5 rounded-full font-mono">{signals.signals.filter(s => s.status === "active").length} активных</span>}
          {!signals.loading && signals.fearGreed.value > 0 && (
            <span className="text-xs font-mono" style={{ color: fgColor(signals.fearGreed.value) }}>F&G: {signals.fearGreed.value}</span>
          )}
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {["Все", "LONG", "SHORT", "Активные"].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-xs px-2.5 py-1 rounded border font-mono transition-colors ${filter === f ? "border-primary text-primary" : "border-border text-muted-foreground hover:border-foreground hover:text-foreground"}`}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {signals.loading ? Array(3).fill(null).map((_, i) => (
          <div key={i} className="panel rounded p-4 fade-in" style={{ animationDelay: `${i * 0.08}s` }}>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-6 bg-secondary rounded animate-pulse" />
              <div><div className="w-24 h-3 bg-secondary rounded animate-pulse mb-1" /><div className="w-16 h-2.5 bg-secondary rounded animate-pulse" /></div>
            </div>
            <div className="flex gap-4">{Array(3).fill(null).map((_, j) => <div key={j} className="w-16 h-8 bg-secondary rounded animate-pulse" />)}</div>
          </div>
        )) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
            <Icon name="Search" size={32} className="opacity-30" />
            <span className="text-sm">Нет сигналов по фильтру</span>
          </div>
        ) : filtered.map((s, i) => (
          <div key={i} className="panel rounded fade-in" style={{ animationDelay: `${i * 0.04}s` }}>
            <div className="p-3 md:p-4 row-hover cursor-pointer" onClick={() => setExpanded(expanded === i ? null : i)}>
              {isMobile ? (
                /* Mobile card layout */
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${s.type === "LONG" ? "badge-bull" : "badge-bear"}`}>{s.type}</span>
                      <span className="font-mono font-semibold text-sm">{s.pair}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${s.status === "active" ? "badge-bull" : "badge-gold"}`}>
                        {s.status === "active" ? "●" : "○"} {s.status === "active" ? "Активен" : "Ожидание"}
                      </span>
                      {s.leverage > 1 && <span className="badge-bear text-xs px-1.5 py-0.5 rounded font-mono font-bold">{s.leverage}x</span>}
                    </div>
                    <Icon name={expanded === i ? "ChevronUp" : "ChevronDown"} size={14} className="text-muted-foreground" />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-secondary/40 rounded p-1.5">
                      <div className="text-xs text-muted-foreground">Вход</div>
                      <div className="font-mono text-xs font-medium">{fmtPrice(s.entry)}</div>
                    </div>
                    <div className="bg-secondary/40 rounded p-1.5">
                      <div className="text-xs text-muted-foreground">Цель</div>
                      <div className="font-mono text-xs bull">{fmtPrice(s.target)}</div>
                    </div>
                    <div className="bg-secondary/40 rounded p-1.5">
                      <div className="text-xs text-muted-foreground">Стоп</div>
                      <div className="font-mono text-xs bear">{fmtPrice(s.stop)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${s.confidence}%`, background: s.confidence > 80 ? "hsl(var(--bull))" : s.confidence > 70 ? "hsl(var(--gold))" : "hsl(var(--bear))" }} />
                    </div>
                    <span className="font-mono text-xs text-muted-foreground">{s.confidence}% AI</span>
                    <span className={`font-mono text-xs ${s.type === "LONG" ? "bull" : "bear"}`}>+{s.potential_pct}%</span>
                    <span className="font-mono text-xs text-muted-foreground">R/R 1:{s.risk_reward}</span>
                  </div>
                </div>
              ) : (
                /* Desktop layout */
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded ${s.type === "LONG" ? "badge-bull" : "badge-bear"}`}>{s.type}</span>
                    <div>
                      <div className="font-mono font-semibold text-sm">{s.pair}</div>
                      <div className="text-xs text-muted-foreground">{s.exchange} · {s.time} UTC</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-5 xl:gap-8">
                    {[{ label: "Вход", val: fmtPrice(s.entry), cls: "" }, { label: "Цель", val: fmtPrice(s.target), cls: "bull" }, { label: "Стоп", val: fmtPrice(s.stop), cls: "bear" }].map((f, fi) => (
                      <div key={fi} className="text-center">
                        <div className="text-xs text-muted-foreground mb-0.5">{f.label}</div>
                        <div className={`font-mono text-sm ${f.cls}`}>{f.val}</div>
                      </div>
                    ))}
                    <div className="text-center">
                      <div className="text-xs text-muted-foreground mb-0.5">Потенциал</div>
                      <div className={`font-mono text-sm ${s.type === "LONG" ? "bull" : "bear"}`}>+{s.potential_pct}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs text-muted-foreground mb-0.5">R/R</div>
                      <div className="font-mono text-sm">1:{s.risk_reward}</div>
                    </div>
                    <div className="text-center min-w-28">
                      <div className="text-xs text-muted-foreground mb-1">Уверенность AI</div>
                      <div className="w-28 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${s.confidence}%`, background: s.confidence > 80 ? "hsl(var(--bull))" : s.confidence > 70 ? "hsl(var(--gold))" : "hsl(var(--bear))" }} />
                      </div>
                      <div className="font-mono text-xs mt-0.5">{s.confidence}%</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {s.leverage > 1 && <span className="badge-bear text-xs px-1.5 py-0.5 rounded font-mono font-bold">{s.leverage}x</span>}
                      <span className={`text-xs px-2 py-0.5 rounded font-mono ${s.status === "active" ? "badge-bull" : "badge-gold"}`}>
                        {s.status === "active" ? "● Активен" : "○ Ожидание"}
                      </span>
                      <Icon name={expanded === i ? "ChevronUp" : "ChevronDown"} size={14} className="text-muted-foreground" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {expanded === i && (
              <div className="px-3 md:px-4 pb-3 md:pb-4 border-t border-border/50 fade-in">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 mb-3">
                  {[
                    { label: "RSI (1h)", val: s.rsi, warn: s.rsi > 70 || s.rsi < 30 },
                    { label: "RSI (4h)", val: s.rsi_4h, warn: s.rsi_4h > 70 || s.rsi_4h < 30 },
                    { label: "MACD", val: s.macd.trend === "bullish" ? "Бычий" : s.macd.trend === "bearish" ? "Медвежий" : "Нейтр.", warn: false },
                    { label: "BB %B", val: s.bollinger.pct_b.toFixed(2), warn: s.bollinger.pct_b > 0.9 || s.bollinger.pct_b < 0.1 },
                  ].map((m, mi) => (
                    <div key={mi} className="text-center p-2 bg-secondary/50 rounded">
                      <div className="text-xs text-muted-foreground mb-0.5">{m.label}</div>
                      <div className={`font-mono text-sm font-semibold ${m.warn ? (s.type === "LONG" ? "bull" : "bear") : ""}`}>{m.val}</div>
                    </div>
                  ))}
                </div>
                <div className="text-xs text-muted-foreground mb-2">Факторы ({s.factors.length}):</div>
                <div className="flex flex-wrap gap-1.5">
                  {s.factors.map((f, fi) => (
                    <span key={fi} className={`text-xs px-2 py-1 rounded border font-mono ${
                      f.includes("LONG") || f.includes("бычий") || f.includes("Бычь") || f.includes("перепроданность") || f.includes("Fear")
                        ? "badge-bull" : f.includes("SHORT") || f.includes("медвежий") || f.includes("Медвеж") || f.includes("перекупленность") || f.includes("Greed")
                        ? "badge-bear" : "border-border text-muted-foreground"}`}>{f}</span>
                  ))}
                </div>
                {s.bollinger.squeeze && (
                  <div className="mt-2 text-xs badge-gold px-3 py-1.5 rounded">⚡ Bollinger Squeeze — ожидается взрывное движение</div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {!signals.loading && signals.signals.length > 0 && (
        <div className="panel rounded p-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
          {[
            { label: "Сигналов", value: String(signals.signals.length) },
            { label: "Ср. уверенность", value: `${Math.round(signals.signals.reduce((a, s) => a + s.confidence, 0) / signals.signals.length)}%` },
            { label: "LONG / SHORT", value: `${signals.signals.filter(s => s.type === "LONG").length} / ${signals.signals.filter(s => s.type === "SHORT").length}` },
            { label: "Fear & Greed", value: String(signals.fearGreed.value) },
          ].map((s, i) => (
            <div key={i}><div className="font-mono text-base font-semibold">{s.value}</div><div className="text-xs text-muted-foreground">{s.label}</div></div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── History ──────────────────────────────────────────────────────────────────

function History() {
  const isMobile = useIsMobile();
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_SIGNALS}?action=saved&limit=50`).then(r => r.json()).then(d => {
      setHistory((d.signals || []).filter((s: any) => s.status === "closed"));
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const totalPnl = history.reduce((acc, h) => acc + (h.pnl_usdt || 0), 0);
  const wins = history.filter(h => h.result === "win").length;
  const losses = history.filter(h => h.result === "loss").length;

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold">История сделок — реальные результаты</span>
        {history.length > 0 && (
          <div className="flex items-center gap-2 font-mono text-xs flex-wrap">
            <span className={totalPnl >= 0 ? "bull" : "bear"}>{totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)} итого</span>
            <span className="text-muted-foreground">|</span>
            <span className="bull">{wins}W</span>
            <span className="bear">{losses}L</span>
          </div>
        )}
      </div>

      <div className="panel rounded overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
            <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-xs font-mono">Загрузка истории...</span>
          </div>
        ) : history.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
            <Icon name="Clock" size={28} className="opacity-30" />
            <span className="text-sm">Пока нет закрытых сделок — AI начал работу сегодня</span>
            <span className="text-xs">Первые результаты появятся через 4 часа</span>
          </div>
        ) : (
          <div>
            {history.map((h, i) => (
              <div key={i} className="mobile-table-row fade-in" style={{ animationDelay: `${i * 0.04}s` }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`font-mono text-xs font-bold ${h.type === "LONG" ? "bull" : "bear"}`}>{h.type}</span>
                    <span className="font-mono text-xs font-medium">{h.pair}</span>
                    <span className="text-xs text-muted-foreground">{h.exchange}</span>
                    {h.leverage > 1 && <span className="badge-bear text-xs px-1 py-0.5 rounded font-mono">{h.leverage}x</span>}
                  </div>
                  <span className="text-xs text-muted-foreground">{h.date}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">Вход: {fmtPrice(h.entry)} · AI {h.confidence}%</span>
                  <div className="flex items-center gap-2">
                    <span className={`font-mono text-sm font-semibold px-2 py-0.5 rounded ${h.result === "win" ? "badge-bull" : "badge-bear"}`}>
                      {h.result === "win" ? "WIN" : "LOSS"} {h.result_pct != null ? `${h.result_pct >= 0 ? "+" : ""}${h.result_pct}%` : ""}
                    </span>
                    {h.pnl_usdt != null && (
                      <span className={`font-mono text-xs font-semibold ${h.pnl_usdt >= 0 ? "bull" : "bear"}`}>
                        {h.pnl_usdt >= 0 ? "+" : ""}${h.pnl_usdt}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {history.length > 0 && (
        <div className="grid grid-cols-3 md:grid-cols-5 gap-2 md:gap-3">
          {[
            { label: "Сделок", value: String(history.length), icon: "Hash", pos: null },
            { label: "Win Rate", value: history.length > 0 ? `${Math.round(wins / history.length * 100)}%` : "—", icon: "Target", pos: wins > losses },
            { label: "Макс. прибыль", value: history.length > 0 ? `+$${Math.max(...history.map(h => h.pnl_usdt || 0)).toFixed(0)}` : "—", icon: "Trophy", pos: true },
            { label: "Итого", value: `${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(0)}`, icon: "TrendingUp", pos: totalPnl >= 0 },
            { label: "Макс. убыток", value: history.length > 0 ? `$${Math.min(...history.map(h => h.pnl_usdt || 0)).toFixed(0)}` : "—", icon: "TrendingDown", pos: false },
          ].map((s, i) => (
            <div key={i} className="panel rounded p-2.5 md:p-3 text-center">
              <Icon name={s.icon} size={12} className={`mx-auto mb-1 ${s.pos === true ? "text-bull" : s.pos === false ? "text-bear" : "text-muted-foreground"}`} />
              <div className={`font-mono text-sm font-semibold ${s.pos === true ? "bull" : s.pos === false ? "bear" : ""}`}>{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Notifications ────────────────────────────────────────────────────────────

function NotificationsSection({ signals }: { signals: SignalsState }) {
  const [read, setRead] = useState<Set<number>>(new Set());
  const items = signals.signals.slice(0, 8).map((s, i) => ({
    id: i, type: s.type === "LONG" ? "signal_long" : "signal_short",
    text: `AI сигнал ${s.type} на ${s.pair} — уверенность ${s.confidence}%`,
    sub: `${s.factors[0] || ""} · Вход: ${fmtPrice(s.entry)}`, time: `${s.time} UTC`, confidence: s.confidence,
  }));
  const staticItems = [
    { id: 100, type: "system", text: "AI движок запущен: анализ 6 пар с Binance", sub: "RSI, MACD, Bollinger, Fear & Greed, дивергенции", time: "сейчас", confidence: null },
    { id: 101, type: "fg", text: `Fear & Greed: ${signals.fearGreed.value} — ${signals.fearGreed.classification}`, sub: "Рыночный сентимент", time: "сейчас", confidence: null },
  ];
  const all = [...items, ...staticItems];
  const unread = all.filter(n => !read.has(n.id)).length;
  const iconMap: Record<string, string> = { signal_long: "TrendingUp", signal_short: "TrendingDown", system: "Bot", fg: "Activity" };
  const colorMap: Record<string, string> = { signal_long: "bull", signal_short: "bear", system: "text-muted-foreground", fg: "gold" };

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">Уведомления</span>
          {unread > 0 && <span className="badge-gold text-xs px-2 py-0.5 rounded-full font-mono">{unread} новых</span>}
        </div>
        <button onClick={() => setRead(new Set(all.map(n => n.id)))} className="text-xs text-muted-foreground hover:text-foreground transition-colors font-mono">
          Все прочитаны
        </button>
      </div>
      {signals.loading ? (
        <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
          <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono">AI анализирует рынок...</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {all.map((n, i) => (
            <div key={n.id}
              className={`panel rounded p-3 md:p-4 flex items-start gap-3 row-hover fade-in cursor-pointer ${!read.has(n.id) ? "border-l-2 border-l-primary" : ""}`}
              style={{ animationDelay: `${i * 0.04}s` }}
              onClick={() => setRead(prev => new Set([...prev, n.id]))}>
              <div className={`mt-0.5 ${colorMap[n.type]}`}><Icon name={iconMap[n.type]} size={14} /></div>
              <div className="flex-1 min-w-0">
                <div className={`text-sm ${read.has(n.id) ? "text-muted-foreground" : "text-foreground"} truncate`}>{n.text}</div>
                <div className="text-xs text-muted-foreground mt-0.5 font-mono">{n.sub}</div>
                <div className="text-xs text-muted-foreground mt-0.5 font-mono">{n.time}</div>
              </div>
              {!read.has(n.id) && <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 blink shrink-0" />}
              {n.confidence && <span className={`text-xs font-mono shrink-0 ${n.confidence >= 80 ? "bull" : n.confidence >= 70 ? "gold" : "bear"}`}>{n.confidence}%</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Analytics ────────────────────────────────────────────────────────────────

function Analytics({ market, signals }: { market: MarketState; signals: SignalsState }) {
  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Аналитика рынка</span>

      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">RSI Обзор (1h) — реальные данные</div>
        {market.loading ? (
          <div className="flex gap-2">{Array(6).fill(null).map((_, i) => <div key={i} className="flex-1 h-14 bg-secondary rounded animate-pulse" />)}</div>
        ) : (
          <div className="flex items-end gap-2 md:gap-3">
            {market.pairs.map((p, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span className="font-mono text-xs" style={{ color: p.rsi > 70 ? "hsl(var(--bear))" : p.rsi < 30 ? "hsl(var(--bull))" : "hsl(var(--foreground))" }}>{p.rsi}</span>
                <div className="w-full rounded-sm" style={{ height: `${(p.rsi / 100) * 60}px`, background: p.rsi > 70 ? "hsl(var(--bear))" : p.rsi < 30 ? "hsl(var(--bull))" : "hsl(43 96% 56%)", opacity: 0.8, minHeight: "4px" }} />
                <span className="text-xs text-muted-foreground font-mono">{p.symbol.replace("/USDT", "")}</span>
                <span className="text-xs font-mono hidden md:block" style={{ color: p.rsi > 70 ? "hsl(var(--bear))" : p.rsi < 30 ? "hsl(var(--bull))" : "hsl(var(--muted-foreground))" }}>
                  {p.rsi > 70 ? "Перекуп." : p.rsi < 30 ? "Перепр." : "Норма"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="panel rounded p-3 md:p-4">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">AI Уверенность</div>
          {signals.loading ? (
            <div className="space-y-2">{Array(4).fill(null).map((_, i) => <div key={i} className="h-6 bg-secondary rounded animate-pulse" />)}</div>
          ) : signals.signals.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">Нет данных</div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {signals.signals.slice(0, 6).map((s, i) => (
                <div key={i} className="flex items-center gap-2 md:gap-3">
                  <span className={`font-mono text-xs font-bold w-8 ${s.type === "LONG" ? "bull" : "bear"}`}>{s.type}</span>
                  <span className="font-mono text-xs w-16 text-muted-foreground">{s.pair.replace("/USDT", "")}</span>
                  <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${s.confidence}%`, background: s.confidence > 80 ? "hsl(var(--bull))" : s.confidence > 70 ? "hsl(var(--gold))" : "hsl(var(--bear))" }} />
                  </div>
                  <span className="font-mono text-xs w-10 text-right">{s.confidence}%</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel rounded p-3 md:p-4">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Сентимент</div>
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Fear & Greed</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-semibold" style={{ color: fgColor(signals.fearGreed.value) }}>
                  {signals.loading ? "..." : signals.fearGreed.value}
                </span>
                <FearGreedGauge value={signals.fearGreed.value} />
              </div>
            </div>
            <div className="text-xs font-mono" style={{ color: fgColor(signals.fearGreed.value) }}>{signals.fearGreed.classification}</div>
            {signals.fearGreed.value <= 25 && <div className="text-xs badge-bull px-2 py-1.5 rounded">Исторически лучшее время для LONG</div>}
            {signals.fearGreed.value >= 80 && <div className="text-xs badge-bear px-2 py-1.5 rounded">Рынок перегрет — риск коррекции</div>}
            {!signals.loading && signals.signals.length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground mb-1">LONG vs SHORT:</div>
                <div className="flex h-2.5 rounded overflow-hidden gap-0.5">
                  <div style={{ flex: signals.signals.filter(s => s.type === "LONG").length, background: "hsl(var(--bull))", opacity: 0.7 }} />
                  <div style={{ flex: signals.signals.filter(s => s.type === "SHORT").length, background: "hsl(var(--bear))", opacity: 0.7 }} />
                </div>
                <div className="flex justify-between text-xs font-mono mt-1">
                  <span className="bull">{signals.signals.filter(s => s.type === "LONG").length} LONG</span>
                  <span className="bear">{signals.signals.filter(s => s.type === "SHORT").length} SHORT</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Обзор топ пары</div>
        {market.loading ? (
          <div className="space-y-2">{Array(5).fill(null).map((_, i) => <div key={i} className="h-7 bg-secondary rounded animate-pulse" />)}</div>
        ) : (
          <div className="flex flex-col gap-2">
            {[...market.pairs].sort((a, b) => Math.abs(b.change) - Math.abs(a.change)).map((p, i) => (
              <div key={i} className="flex items-center gap-2 md:gap-4">
                <span className="font-mono text-xs text-muted-foreground w-4">{i + 1}</span>
                <span className="font-mono text-xs font-medium w-20">{p.symbol}</span>
                <div className="flex-1 relative h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(Math.abs(p.change) * 8, 100)}%`, background: p.change >= 0 ? "hsl(var(--bull))" : "hsl(var(--bear))" }} />
                </div>
                <span className={`font-mono text-xs w-14 text-right ${p.change >= 0 ? "bull" : "bear"}`}>{p.change >= 0 ? "+" : ""}{p.change.toFixed(2)}%</span>
                <span className="font-mono text-xs text-muted-foreground w-16 text-right hidden sm:block">{fmtVolume(p.volume)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Settings ─────────────────────────────────────────────────────────────────

function Settings({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Настройки</span>
      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Источники данных</div>
        {[
          { name: "Binance Public API", desc: "Цены, свечи, объёмы", status: true },
          { name: "Alternative.me", desc: "Fear & Greed Index", status: true },
          { name: "AI Signal Engine", desc: "RSI, MACD, Bollinger, тренд", status: true },
        ].map((e, i) => (
          <div key={i} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
            <div>
              <div className="text-sm font-medium">{e.name}</div>
              <div className="text-xs text-muted-foreground">{e.desc}</div>
            </div>
            <span className={`text-xs font-mono px-2 py-0.5 rounded ${e.status ? "badge-bull" : "badge-bear"}`}>● Активно</span>
          </div>
        ))}
      </div>
      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">AI Параметры</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            { label: "Мин. уверенность сигнала", value: "90", unit: "%" },
            { label: "Период обновления", value: "5", unit: "мин" },
            { label: "ATR множитель TP", value: "3.5", unit: "x" },
            { label: "ATR множитель SL", value: "1.4", unit: "x" },
          ].map((s, i) => (
            <div key={i}>
              <label className="text-xs text-muted-foreground block mb-1">{s.label}</label>
              <div className="flex items-center gap-2">
                <input type="text" defaultValue={s.value} className="flex-1 bg-secondary border border-border rounded px-2 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:border-primary" />
                {s.unit && <span className="text-xs text-muted-foreground">{s.unit}</span>}
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          <button onClick={onRefresh} className="text-xs px-4 py-2 bg-primary text-primary-foreground rounded font-mono hover:opacity-80 transition-opacity flex items-center gap-2">
            <Icon name="RefreshCw" size={12} />Обновить данные
          </button>
          <button className="text-xs px-4 py-2 border border-border text-muted-foreground rounded font-mono hover:text-foreground transition-colors">
            Сохранить
          </button>
        </div>
      </div>
      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">AI Алгоритм</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
          {[
            { factor: "RSI (1h + 4h)", weight: "20%", desc: "Перекупленность / перепроданность" },
            { factor: "MACD", weight: "15%", desc: "Импульс и направление тренда" },
            { factor: "Bollinger Bands", weight: "15%", desc: "%B позиция + Squeeze" },
            { factor: "EMA Тренд", weight: "20%", desc: "EMA20/50 + сила" },
            { factor: "Объём", weight: "10%", desc: "Подтверждение движения" },
            { factor: "Fear & Greed", weight: "10%", desc: "Рыночный сентимент" },
            { factor: "Дивергенции RSI", weight: "10%", desc: "Бычьи / медвежьи" },
          ].map((f, i) => (
            <div key={i} className="flex items-start gap-2 p-2 bg-secondary/50 rounded">
              <span className="badge-gold text-xs px-1.5 py-0.5 rounded font-mono shrink-0">{f.weight}</span>
              <div><div className="font-medium">{f.factor}</div><div className="text-muted-foreground">{f.desc}</div></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Statistics ──────────────────────────────────────────────────────────────

function StatisticsSection() {
  const [stats, setStats] = useState<any>(null);
  const [saved, setSaved] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const isMobile = useIsMobile();

  useEffect(() => {
    Promise.all([
      fetch(`${API_SIGNALS}?action=stats`).then(r => r.json()),
      fetch(`${API_SIGNALS}?action=saved&limit=20`).then(r => r.json()),
    ]).then(([s, sg]) => {
      setStats(s.stats || null);
      setPortfolio(s.stats?.portfolio || null);
      setSaved(sg.signals || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const fmtPct = (v: number | null) => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  if (loading) return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Честная статистика</span>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {Array(8).fill(null).map((_, i) => <div key={i} className="panel rounded p-3 h-16 animate-pulse bg-secondary" />)}
      </div>
    </div>
  );

  const s = stats || {};
  const winRate = s.win_rate || 0;
  const winColor = winRate >= 60 ? "bull" : winRate >= 45 ? "gold" : "bear";
  const p = portfolio || {};
  const growthPct = p.pnl_pct || 0;
  const growthX = p.balance && p.initial ? (p.balance / p.initial).toFixed(2) : "1.00";

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Честная статистика — только реальные закрытые сигналы</span>
        <span className="text-xs text-muted-foreground font-mono badge-gold px-2 py-0.5 rounded">100% прозрачность</span>
      </div>

      {/* Portfolio banner */}
      <div className="panel rounded p-4 md:p-5 border border-primary/20" style={{ background: "linear-gradient(135deg, hsl(220 13% 9%), hsl(158 64% 48% / 0.05))" }}>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Виртуальный портфель · старт $1,000 · 14 апр 2026</div>
            <div className="font-mono text-2xl md:text-3xl font-bold bull">${p.balance ? p.balance.toLocaleString("en-US", { minimumFractionDigits: 2 }) : "1,000.00"}</div>
            <div className="flex items-center gap-3 mt-1 flex-wrap">
              <span className={`font-mono text-sm font-semibold ${growthPct >= 0 ? "bull" : "bear"}`}>{growthPct >= 0 ? "+" : ""}{growthPct.toFixed(2)}%</span>
              <span className="font-mono text-sm text-muted-foreground">×{growthX}</span>
              {p.pnl != null && <span className={`font-mono text-sm ${p.pnl >= 0 ? "bull" : "bear"}`}>{p.pnl >= 0 ? "+" : ""}${p.pnl?.toFixed(2) || "0.00"}</span>}
              {p.drawdown > 0 && <span className="font-mono text-xs bear">Просадка: -{p.drawdown.toFixed(2)}%</span>}
            </div>
          </div>
          {/* Mini growth chart */}
          {p.daily && p.daily.length > 1 && (
            <div className="w-40 h-12">
              <svg width="100%" height="100%" viewBox="0 0 160 48" preserveAspectRatio="none">
                {(() => {
                  const pts = p.daily.map((d: any) => d.balance);
                  const min = Math.min(...pts) * 0.995; const max = Math.max(...pts) * 1.005;
                  const path = pts.map((v: number, i: number) => `${(i / (pts.length - 1)) * 160},${48 - ((v - min) / (max - min || 1)) * 44}`).join(" ");
                  return <polyline points={path} fill="none" stroke="hsl(158 64% 48%)" strokeWidth="2" />;
                })()}
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: "Всего сигналов", value: String(s.total || 0), icon: "Hash", cls: "" },
          { label: "Win Rate", value: `${winRate}%`, icon: "Target", cls: winColor },
          { label: "Побед / Потерь", value: `${s.wins || 0} / ${s.losses || 0}`, icon: "TrendingUp", cls: "" },
          { label: "В ожидании", value: String(s.pending || 0), icon: "Clock", cls: "gold" },
          { label: "Ср. прибыль (с плечом)", value: fmtPct(s.avg_win), icon: "ArrowUpRight", cls: "bull" },
          { label: "Ср. убыток", value: fmtPct(s.avg_loss), icon: "ArrowDownRight", cls: "bear" },
          { label: "Лучшая сделка", value: fmtPct(s.best_trade), icon: "Trophy", cls: "bull" },
          { label: "Мат. ожидание", value: fmtPct(s.expectancy), icon: "BarChart2", cls: s.expectancy > 0 ? "bull" : "bear" },
        ].map((m, i) => (
          <div key={i} className="panel rounded p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground">{m.label}</span>
              <Icon name={m.icon} size={11} className="text-muted-foreground" />
            </div>
            <div className={`font-mono text-base font-semibold ${m.cls}`}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Win rate bar */}
      {s.closed > 0 && (
        <div className="panel rounded p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Результативность по закрытым сигналам ({s.closed} сделок)</span>
            <span className={`font-mono text-sm font-semibold ${winColor}`}>{winRate}%</span>
          </div>
          <div className="flex h-3 rounded overflow-hidden gap-0.5">
            <div style={{ flex: s.wins, background: "hsl(var(--bull))", opacity: 0.8 }} title={`${s.wins} побед`} />
            <div style={{ flex: s.losses, background: "hsl(var(--bear))", opacity: 0.8 }} title={`${s.losses} потерь`} />
          </div>
          <div className="flex justify-between text-xs font-mono mt-1">
            <span className="bull">{s.wins} WIN</span>
            <span className="bear">{s.losses} LOSS</span>
          </div>
        </div>
      )}

      {/* By pair */}
      {s.by_pair && s.by_pair.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Статистика по парам</div>
          <div className="flex flex-col gap-2">
            {s.by_pair.map((p: any, i: number) => {
              const wr = p.total > 0 ? Math.round(p.wins / p.total * 100) : 0;
              return (
                <div key={i} className="flex items-center gap-3">
                  <span className="font-mono text-xs w-20">{p.pair}</span>
                  <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${wr}%`, background: wr >= 60 ? "hsl(var(--bull))" : wr >= 40 ? "hsl(var(--gold))" : "hsl(var(--bear))" }} />
                  </div>
                  <span className="font-mono text-xs w-10 text-right">{wr}%</span>
                  <span className={`font-mono text-xs w-14 text-right ${p.avg_pct >= 0 ? "bull" : "bear"}`}>{p.avg_pct >= 0 ? "+" : ""}{p.avg_pct}%</span>
                  <span className="text-xs text-muted-foreground w-12 text-right">{p.wins}/{p.total}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent signals with results */}
      <div className="panel rounded overflow-hidden">
        <div className="px-3 py-2 border-b border-border flex items-center justify-between">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Последние сигналы (реальная история)</span>
          <span className="text-xs font-mono text-muted-foreground">Порог: 90%+</span>
        </div>
        {saved.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
            <Icon name="Clock" size={28} className="opacity-30" />
            <span className="text-sm">История накапливается — AI анализирует 25 пар</span>
          </div>
        ) : (
          <div>
            {saved.map((sig, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 md:gap-4 px-3 py-2.5 border-b border-border/40 row-hover fade-in text-xs font-mono"
                style={{ animationDelay: `${i * 0.03}s` }}>
                <span className={`font-bold w-10 ${sig.type === "LONG" ? "bull" : "bear"}`}>{sig.type}</span>
                <span className="font-medium w-24">{sig.pair}</span>
                <span className="text-muted-foreground w-14">{sig.exchange}</span>
                <span className="text-muted-foreground">{sig.date}</span>
                <span>вход: {fmtPrice(sig.entry)}</span>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${sig.confidence >= 92 ? "badge-bull" : "badge-gold"}`}>{sig.confidence}% AI</span>
                  {sig.leverage > 1 && <span className="badge-bear text-xs px-1.5 py-0.5 rounded">{sig.leverage}x</span>}
                  {sig.position_size > 0 && <span className="text-muted-foreground">${sig.position_size}</span>}
                </div>
                {sig.result ? (
                  <span className={`font-semibold px-2 py-0.5 rounded ${sig.result === "win" ? "badge-bull" : "badge-bear"}`}>
                    {sig.result === "win" ? "WIN" : "LOSS"} {sig.result_pct != null ? `${sig.result_pct >= 0 ? "+" : ""}${sig.result_pct}%` : ""}
                    {sig.pnl_usdt != null && <span className="ml-1">{sig.pnl_usdt >= 0 ? "+" : ""}${sig.pnl_usdt}</span>}
                  </span>
                ) : (
                  <span className="badge-gold text-xs px-2 py-0.5 rounded">⏳ Открыт</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel rounded p-3 text-xs text-muted-foreground">
        <div className="flex items-start gap-2">
          <Icon name="Info" size={12} className="text-primary shrink-0 mt-0.5" />
          <span>Все сигналы сохраняются в базе данных автоматически. Результат (WIN/LOSS) определяется по реальной цене через 4 часа: достиг TP → WIN, достиг SL → LOSS, иначе — по текущей цене. Никаких ручных корректировок — <strong className="text-foreground">100% честно</strong>.</span>
        </div>
      </div>
    </div>
  );
}

// ─── Auto Trade ───────────────────────────────────────────────────────────────

function AutoTradeSection({ signals }: { signals: SignalsState }) {
  const [botStats, setBotStats] = useState<any>(null);
  const [balances, setBalances] = useState<Record<string, any>>({});
  const [configs, setConfigs] = useState<Record<string, { mode: string; active: boolean; max_pos: number }>>({
    Binance: { mode: "medium", active: false, max_pos: 50 },
    Bybit:   { mode: "medium", active: false, max_pos: 50 },
    OKX:     { mode: "medium", active: false, max_pos: 50 },
    MEXC:    { mode: "medium", active: false, max_pos: 50 },
  });
  const [loading, setLoading] = useState(true);
  const [trading, setTrading] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [autoMode, setAutoMode] = useState(() => localStorage.getItem("bot_auto_247") === "true");
  const [nextRun, setNextRun] = useState<string>("");
  const [runCount, setRunCount] = useState(0);
  const isMobile = useIsMobile();

  const runAutoBot = async () => {
    try {
      const res = await fetch(`${API_TRADE}?action=auto_run`).then(r => r.json());
      setLastResult({ ...res, ts: new Date().toLocaleTimeString("ru-RU"), auto: true });
      setRunCount(prev => prev + 1);
      fetch(`${API_TRADE}?action=stats`).then(r => r.json()).then(setBotStats);
      return res;
    } catch { return null; }
  };

  useEffect(() => {
    fetch(`${API_TRADE}?action=stats`).then(r => r.json()).then(d => {
      setBotStats(d);
      setLoading(false);
    }).catch(() => setLoading(false));
    fetch(`${API_TRADE}?action=config`).then(r => r.json()).then(d => {
      if (d.configs && d.configs.length > 0) {
        setConfigs(prev => {
          const newCfg = {...prev};
          d.configs.forEach((c: any) => { newCfg[c.exchange] = { mode: c.mode, active: c.active, max_pos: c.max_position }; });
          return newCfg;
        });
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!autoMode) return;
    runAutoBot();
    const interval = setInterval(() => { runAutoBot(); }, 5 * 60 * 1000);
    const countdown = setInterval(() => {
      const now = Date.now();
      const next = Math.ceil(now / (5 * 60 * 1000)) * (5 * 60 * 1000);
      const diff = Math.max(0, Math.floor((next - now) / 1000));
      const m = Math.floor(diff / 60); const s = diff % 60;
      setNextRun(`${m}:${s.toString().padStart(2, "0")}`);
    }, 1000);
    return () => { clearInterval(interval); clearInterval(countdown); };
  }, [autoMode]);

  const saveConfig = async (exchange: string, mode: string, active: boolean, max_pos: number) => {
    await fetch(API_TRADE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save_config", exchange, mode, max_position: max_pos, active }),
    });
  };

  const checkBalance = async (exchange: string) => {
    const res = await fetch(`${API_TRADE}?action=balance&exchange=${exchange}`).then(r => r.json());
    setBalances(prev => ({ ...prev, [exchange]: res }));
  };

  const handleTrade = async (exchange: string, signal: any) => {
    const cfg = configs[exchange];
    if (!cfg.active) return;
    setTrading(`${exchange}-${signal.pair}`);
    try {
      const res = await fetch(API_TRADE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "trade", exchange, mode: cfg.mode, signal }),
      }).then(r => r.json());
      setLastResult({ exchange, signal: signal.pair, ...res, ts: new Date().toLocaleTimeString("ru-RU") });
      fetch(`${API_TRADE}?action=stats`).then(r => r.json()).then(setBotStats);
    } finally {
      setTrading(null);
    }
  };

  const MODES = {
    medium: { label: "MEDIUM", color: "badge-gold", desc: "5% депозита · 2x плечо · макс 3 сделки · порог 90% · цель +5%/день" },
    hard:   { label: "HARD",   color: "badge-bear",  desc: "20% депозита · 5x плечо · макс 5 сделок · порог 85% · цель +15%/день" },
  };

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Авто-Торговля</span>
        <div className="flex items-center gap-2">
          {botStats?.today_pnl > 0 && <span className="text-xs badge-bull px-2 py-0.5 rounded font-mono">+${botStats.today_pnl} сегодня</span>}
          <span className="text-xs badge-bear px-2 py-0.5 rounded font-mono">⚠ Реальные деньги</span>
        </div>
      </div>

      {/* Auto-run banner */}
      <div className={`panel rounded p-4 border ${autoMode ? "border-primary/40" : "border-border"}`} style={{ background: autoMode ? "linear-gradient(135deg, hsl(220 13% 9%), hsl(158 64% 48% / 0.06))" : "linear-gradient(135deg, hsl(220 13% 9%), hsl(217 91% 60% / 0.03))" }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {autoMode && <div className="w-2 h-2 rounded-full bg-primary blink" />}
              <div className="text-xs text-muted-foreground uppercase tracking-wider">
                {autoMode ? "Бот работает 24/7" : "Автономный режим"}
              </div>
            </div>
            <div className="text-sm">
              {autoMode
                ? <>Каждые 5 мин: анализ → сделки → Telegram. {nextRun && <span className="font-mono text-muted-foreground">Следующий цикл: {nextRun}</span>}</>
                : "Бот торгует 24/7 независимо от того, открыт сайт или нет"}
            </div>
            {autoMode && runCount > 0 && (
              <div className="text-xs text-muted-foreground font-mono mt-1">Циклов выполнено: {runCount}</div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <span className="text-xs font-mono font-bold">{autoMode ? "24/7 ВКЛ" : "ВЫКЛ"}</span>
              <div
                onClick={() => {
                  const next = !autoMode;
                  setAutoMode(next);
                  localStorage.setItem("bot_auto_247", String(next));
                }}
                className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer ${autoMode ? "bg-primary" : "bg-secondary"}`}>
                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${autoMode ? "left-7" : "left-1"}`} />
              </div>
            </label>
          </div>
        </div>
        {lastResult?.auto && (
          <div className="mt-3 pt-3 border-t border-border text-xs font-mono text-muted-foreground flex flex-wrap gap-3">
            <span>Сигналов: {lastResult.checked || 0}</span>
            <span className="bull">Открыто: {lastResult.opened || 0}</span>
            <span>Закрыто: {lastResult.closed || 0}</span>
            {lastResult.skipped_target > 0 && <span className="gold">План +15% выполнен!</span>}
            <span>@ {lastResult.ts}</span>
          </div>
        )}
      </div>

      {/* Warning */}
      <div className="panel rounded p-3 border border-amber-600/30 bg-amber-600/5">
        <div className="flex items-start gap-2">
          <Icon name="AlertTriangle" size={14} className="text-amber-500 shrink-0 mt-0.5" />
          <div className="text-xs text-muted-foreground">
            <strong className="text-amber-500">Автономный бот:</strong> торгует реальными деньгами. Цель HARD: <strong className="text-foreground">+15% в день</strong>.
            При достижении плана — останавливается до завтра. При убытке &gt;5% — автостоп. Уведомления в Telegram.
          </div>
        </div>
      </div>

      {/* Bot Stats */}
      {botStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Открытых сделок", value: String(botStats.open || 0), cls: botStats.open > 0 ? "gold" : "" },
            { label: "Win Rate", value: `${botStats.win_rate || 0}%`, cls: botStats.win_rate >= 60 ? "bull" : "bear" },
            { label: "Общий P&L", value: `${botStats.total_pnl >= 0 ? "+" : ""}$${botStats.total_pnl || 0}`, cls: botStats.total_pnl >= 0 ? "bull" : "bear" },
            { label: "Всего сделок", value: String(botStats.total || 0), cls: "" },
          ].map((m, i) => (
            <div key={i} className="panel rounded p-3">
              <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
              <div className={`font-mono text-base font-semibold ${m.cls}`}>{m.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Exchange connections */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {["Binance", "Bybit", "OKX", "MEXC"].map(exch => {
          const cfg = configs[exch];
          const bal = balances[exch];
          const mode = MODES[cfg.mode as keyof typeof MODES];
          return (
            <div key={exch} className={`panel rounded p-3 md:p-4 flex flex-col gap-3 ${cfg.active ? "border-primary/30" : ""}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${cfg.active ? "bg-primary blink" : "bg-secondary"}`} />
                  <span className="font-mono font-semibold text-sm">{exch}</span>
                </div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <span className="text-xs text-muted-foreground">Вкл.</span>
                  <div
                    onClick={() => { const newActive = !cfg.active; setConfigs(prev => ({ ...prev, [exch]: { ...prev[exch], active: newActive } })); saveConfig(exch, cfg.mode, newActive, cfg.max_pos); }}
                    className={`w-9 h-5 rounded-full transition-colors relative cursor-pointer ${cfg.active ? "bg-primary" : "bg-secondary"}`}>
                    <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all ${cfg.active ? "left-4" : "left-0.5"}`} />
                  </div>
                </label>
              </div>

              {/* Mode selector */}
              <div className="flex gap-2">
                {["medium", "hard"].map(m => (
                  <button key={m} onClick={() => { setConfigs(prev => ({ ...prev, [exch]: { ...prev[exch], mode: m } })); saveConfig(exch, m, cfg.active, cfg.max_pos); }}
                    className={`flex-1 text-xs py-1.5 rounded border font-mono font-bold transition-colors ${cfg.mode === m ? MODES[m as keyof typeof MODES].color : "border-border text-muted-foreground hover:border-foreground"}`}>
                    {MODES[m as keyof typeof MODES].label}
                  </button>
                ))}
              </div>
              <div className="text-xs text-muted-foreground">{mode.desc}</div>

              {/* Balance */}
              {bal ? (
                bal.ok ? (
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-muted-foreground">Баланс USDT:</span>
                    <span className="bull font-semibold">${bal.usdt}</span>
                  </div>
                ) : (
                  <div className="text-xs bear">{bal.error}</div>
                )
              ) : (
                <button onClick={() => checkBalance(exch)}
                  className="text-xs px-3 py-1.5 border border-border rounded font-mono hover:border-foreground transition-colors text-muted-foreground">
                  Проверить баланс
                </button>
              )}

              {/* Trade buttons for top signals */}
              {cfg.active && signals.signals.length > 0 && (
                <div className="flex flex-col gap-1.5 border-t border-border pt-2">
                  <div className="text-xs text-muted-foreground mb-1">Топ сигналы для торговли:</div>
                  {signals.signals.slice(0, 2).map((sig, si) => (
                    <button key={si}
                      onClick={() => handleTrade(exch, sig)}
                      disabled={!!trading}
                      className={`text-xs px-2 py-1.5 rounded border font-mono flex items-center justify-between transition-colors disabled:opacity-50 ${sig.type === "LONG" ? "badge-bull hover:opacity-80" : "badge-bear hover:opacity-80"}`}>
                      <span>{sig.type} {sig.pair}</span>
                      <span>{sig.confidence}% · {sig.type === "LONG" ? "+" : "-"}{sig.potential_pct}%</span>
                      {trading === `${exch}-${sig.pair}` && (
                        <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin ml-1" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Last result */}
      {lastResult && (
        <div className={`panel rounded p-3 border ${lastResult.ok ? "border-bull/30" : "border-bear/30"} fade-in`}>
          <div className="flex items-center gap-2">
            <Icon name={lastResult.ok ? "CheckCircle" : "XCircle"} size={14} className={lastResult.ok ? "bull" : "bear"} />
            <span className="font-mono text-xs">
              {lastResult.ok
                ? `✓ Сделка открыта: ${lastResult.exchange} ${lastResult.signal} $${lastResult.position_usdt} · ${lastResult.ts}`
                : `✗ Ошибка: ${lastResult.error} · ${lastResult.ts}`}
            </span>
          </div>
        </div>
      )}

      {/* Open trades */}
      {botStats?.open_trades?.length > 0 && (
        <div className="panel rounded overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Открытые сделки бота</span>
          </div>
          {botStats.open_trades.map((t: any, i: number) => (
            <div key={i} className="flex flex-wrap items-center gap-3 px-3 py-2.5 border-b border-border/40 row-hover text-xs font-mono">
              <span className={`font-bold ${t.direction === "LONG" ? "bull" : "bear"}`}>{t.direction}</span>
              <span>{t.pair}</span>
              <span className="text-muted-foreground">{t.exchange}</span>
              <span className={`px-1.5 py-0.5 rounded ${t.mode === "hard" ? "badge-bear" : "badge-gold"}`}>{t.mode.toUpperCase()}</span>
              <span>вход: {fmtPrice(t.entry)}</span>
              <span className="text-muted-foreground">${t.position_usdt}</span>
              <span className="text-muted-foreground ml-auto">{t.opened_at}</span>
            </div>
          ))}
        </div>
      )}

      {/* API Keys guide */}
      <div className="panel rounded p-3 md:p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Как подключить биржу</div>
        <div className="flex flex-col gap-2 text-xs">
          {[
            { exch: "Binance", steps: ["binance.com → Профиль → API Management", "Создать API ключ → включить Spot Trading", "Добавить IP в whitelist (опционально)", "Вставить BINANCE_API_KEY и BINANCE_SECRET_KEY в Секреты"] },
            { exch: "Bybit", steps: ["bybit.com → Аккаунт → API Management", "Создать новый ключ → Unified Trading", "Добавить BYBIT_API_KEY и BYBIT_SECRET_KEY в Секреты"] },
            { exch: "OKX", steps: ["okx.com → Аккаунт → API Keys → Создать", "Добавить OKX_API_KEY, OKX_SECRET_KEY и OKX_PASSPHRASE в Секреты"] },
            { exch: "MEXC", steps: ["mexc.com → Профиль → API Management", "Создать API → включить Spot Trading", "Добавить MEXC_API_KEY и MEXC_SECRET_KEY в Секреты"] },
          ].map((e, i) => (
            <details key={i} className="border border-border rounded">
              <summary className="px-3 py-2 cursor-pointer font-medium text-foreground">{e.exch} — инструкция</summary>
              <div className="px-3 pb-3 flex flex-col gap-1">
                {e.steps.map((step, si) => (
                  <div key={si} className="flex items-start gap-2 text-muted-foreground">
                    <span className="badge-gold px-1.5 rounded font-mono shrink-0">{si + 1}</span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Ticker ───────────────────────────────────────────────────────────────────

function TickerTape({ pairs }: { pairs: PairData[] }) {
  const items = pairs.length > 0 ? [...pairs, ...pairs] : [];
  if (items.length === 0) return null;
  return (
    <div className="overflow-hidden border-b border-border shrink-0" style={{ background: "hsl(220 13% 7%)" }}>
      <div className="ticker-scroll inline-flex gap-6 py-1.5 px-4">
        {items.map((p, i) => (
          <div key={i} className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="font-mono text-xs text-muted-foreground">{p.symbol}</span>
            <span className="font-mono text-xs">{fmtPrice(p.price)}</span>
            <span className={`font-mono text-xs ${p.change >= 0 ? "bull" : "bear"}`}>{p.change >= 0 ? "▲" : "▼"}{Math.abs(p.change).toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

const NAV = [
  { id: "dashboard", label: "Дашборд", icon: "LayoutDashboard" },
  { id: "signals", label: "Сигналы", icon: "Zap" },
  { id: "stats", label: "Статистика", icon: "BarChart2" },
  { id: "autotrade", label: "Авто-бот", icon: "Bot" },
  { id: "history", label: "История", icon: "History" },
  { id: "analytics", label: "Аналитика", icon: "TrendingUp" },
  { id: "notifications", label: "Уведомления", icon: "Bell" },
  { id: "settings", label: "Настройки", icon: "Settings" },
];

export default function Index() {
  const [active, setActive] = useState("dashboard");
  const [market, setMarket] = useState<MarketState>({ pairs: [], updatedAt: "", loading: true });
  const [signals, setSignals] = useState<SignalsState>({ signals: [], fearGreed: { value: 50, classification: "Neutral" }, loading: true, generatedAt: "" });
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const isMobile = useIsMobile();

  const fetchMarket = useCallback(async () => {
    try {
      const res = await fetch(`${API_MARKET}?action=all`);
      const data = await res.json();
      if (data.pairs) setMarket({ pairs: data.pairs, updatedAt: data.updated_at || "", loading: false });
    } catch { setMarket(prev => ({ ...prev, loading: false })); }
  }, []);

  const fetchSignals = useCallback(async () => {
    try {
      const res = await fetch(`${API_SIGNALS}?action=generate`);
      const data = await res.json();
      if (data.signals !== undefined) setSignals({ signals: data.signals || [], fearGreed: data.fear_greed || { value: 50, classification: "Neutral" }, loading: false, generatedAt: data.generated_at || "" });
    } catch { setSignals(prev => ({ ...prev, loading: false })); }
  }, []);

  const refresh = useCallback(() => {
    setMarket(prev => ({ ...prev, loading: true }));
    setSignals(prev => ({ ...prev, loading: true }));
    setLastUpdate(new Date());
    fetchMarket();
    fetchSignals();
  }, [fetchMarket, fetchSignals]);

  useEffect(() => { fetchMarket(); fetchSignals(); }, []);
  useEffect(() => { const t = setInterval(refresh, 5 * 60 * 1000); return () => clearInterval(t); }, [refresh]);

  const unread = signals.signals.length;
  const btc = market.pairs[0];

  const renderSection = () => {
    switch (active) {
      case "dashboard": return <Dashboard market={market} signals={signals} />;
      case "signals": return <Signals signals={signals} />;
      case "stats": return <StatisticsSection />;
      case "autotrade": return <AutoTradeSection signals={signals} />;
      case "history": return <History />;
      case "analytics": return <Analytics market={market} signals={signals} />;
      case "notifications": return <NotificationsSection signals={signals} />;
      case "settings": return <Settings onRefresh={refresh} />;
      default: return <Dashboard market={market} signals={signals} />;
    }
  };

  return (
    <div className={`flex flex-col ${isMobile ? "min-h-screen" : "h-screen overflow-hidden"}`}>
      {/* Header */}
      <header className="flex items-center justify-between px-3 md:px-4 py-2 border-b border-border shrink-0" style={{ background: "hsl(220 13% 7%)" }}>
        <div className="flex items-center gap-2 md:gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-5 rounded bg-primary flex items-center justify-center">
              <Icon name="Bot" size={12} className="text-primary-foreground" />
            </div>
            <span className="font-mono font-semibold text-sm tracking-tight">TradeBot AI</span>
          </div>
          {!isMobile && (
            <>
              <div className="w-px h-4 bg-border" />
              <span className="text-xs text-muted-foreground font-mono">World-Class Signal Engine</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2 md:gap-3">
          {btc && !isMobile && (
            <>
              <span className="font-mono text-xs">BTC <span className={btc.change >= 0 ? "bull" : "bear"}>${fmtPrice(btc.price)}</span></span>
              <div className="w-px h-4 bg-border" />
            </>
          )}
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <div className={`w-1.5 h-1.5 rounded-full blink ${market.loading || signals.loading ? "bg-gold" : "bg-bull"}`} />
            {!isMobile && <span className="text-muted-foreground">{market.loading || signals.loading ? "обновление..." : "актуальны"}</span>}
          </div>
          <button onClick={refresh} disabled={market.loading || signals.loading}
            className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors disabled:opacity-40">
            <Icon name="RefreshCw" size={12} className={market.loading || signals.loading ? "animate-spin" : ""} />
          </button>
          {!isMobile && (
            <button className="text-xs font-mono px-2.5 py-1 rounded border transition-colors"
              style={{ background: "hsl(158 64% 48% / 0.08)", borderColor: "hsl(158 64% 48% / 0.3)", color: "hsl(var(--bull))" }}>
              ● AI АКТИВЕН
            </button>
          )}
        </div>
      </header>

      {/* Ticker */}
      <TickerTape pairs={market.pairs} />

      {/* Body */}
      <div className={`flex flex-1 ${isMobile ? "flex-col" : "overflow-hidden"}`}>
        {/* Desktop Sidebar */}
        {!isMobile && (
          <aside className="w-44 border-r border-border shrink-0 flex flex-col" style={{ background: "hsl(var(--sidebar-background))" }}>
            <nav className="flex-1 py-2">
              {NAV.map(item => (
                <button key={item.id} onClick={() => setActive(item.id)}
                  className={`nav-item w-full flex items-center gap-3 px-4 py-2.5 text-left ${active === item.id ? "nav-active" : "text-sidebar-foreground"}`}>
                  <Icon name={item.icon} size={14} />
                  <span className="text-xs font-medium">{item.label}</span>
                  {item.id === "notifications" && unread > 0 && !signals.loading && (
                    <span className="ml-auto text-xs font-mono bg-primary text-primary-foreground rounded-full w-4 h-4 flex items-center justify-center leading-none">{Math.min(unread, 9)}</span>
                  )}
                  {item.id === "signals" && signals.loading && (
                    <div className="ml-auto w-3 h-3 border border-primary border-t-transparent rounded-full animate-spin" />
                  )}
                </button>
              ))}
            </nav>
            <div className="border-t border-border p-3">
              <div className="text-xs text-muted-foreground font-mono space-y-1">
                <div className="flex justify-between"><span>Сигналов:</span><span className="text-foreground">{signals.loading ? "..." : signals.signals.length}</span></div>
                <div className="flex justify-between"><span>F&G:</span><span style={{ color: fgColor(signals.fearGreed.value) }}>{signals.loading ? "..." : signals.fearGreed.value}</span></div>
              </div>
            </div>
          </aside>
        )}

        {/* Main Content */}
        <main className={`flex-1 overflow-y-auto p-3 md:p-4 ${isMobile ? "pb-20" : ""}`}>
          {renderSection()}
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      {isMobile && (
        <nav className="fixed bottom-0 left-0 right-0 border-t border-border z-50 flex" style={{ background: "hsl(220 13% 7%)" }}>
          {NAV.map(item => (
            <button key={item.id} onClick={() => setActive(item.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-colors relative ${active === item.id ? "text-primary" : "text-muted-foreground"}`}>
              <Icon name={item.icon} size={18} />
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
              {item.id === "notifications" && unread > 0 && !signals.loading && (
                <span className="absolute top-1.5 right-1/4 bg-primary text-primary-foreground text-[9px] rounded-full w-3.5 h-3.5 flex items-center justify-center font-bold">{Math.min(unread, 9)}</span>
              )}
              {active === item.id && <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-primary rounded-full" />}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}