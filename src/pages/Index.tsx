/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback, useRef } from "react";
import Icon from "@/components/ui/icon";

const API_SIGNALS  = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed";
const API_MARKET   = "https://functions.poehali.dev/b4830b16-e61f-4ab5-8a8b-eb323709567c";
const API_MEXC_BOT = "https://functions.poehali.dev/d798c17a-255c-4fb0-869f-37ff1213fbbe";

// ─── Types ────────────────────────────────────────────────────────────────────

interface PumpSignal {
  id?: number;
  pair: string;
  type: "Pump" | "Dump";
  exchange: string;
  price_now: number;
  price_from: number;
  price_pct: number;
  volume_usd: number;
  volume_pct: number;
  volume_increase_usd?: number;
  score: number;
  strength?: number;
  timeframe: string;
  time: string;
  date?: string;
  reasoning?: string;
  factors?: string[];
  result?: string;
  result_pct?: number;
  pnl_usdt?: number;
  entry?: number;
  tp1?: number; tp2?: number; tp3?: number; sl?: number;
  tp1_pct?: number; tp2_pct?: number; tp3_pct?: number; sl_pct?: number;
  leverage?: number;
  position_usdt?: number;
  rvol?: number;
  rsi?: number;
  pct_1?: number; pct_3?: number; pct_6?: number;
  analysis?: string;
}

interface MarketPair {
  symbol: string;
  price: number;
  change: number;
  volume: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fp(p: number): string {
  if (!p) return "—";
  if (p >= 10000) return p.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (p >= 100)   return p.toFixed(2);
  if (p >= 1)     return p.toFixed(4);
  if (p >= 0.001) return p.toFixed(6);
  return p.toFixed(8);
}

function fv(v: number): string {
  if (!v) return "$0";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function scoreColor(s: number): string {
  if (s >= 85) return "hsl(158 64% 48%)";
  if (s >= 75) return "hsl(120 60% 50%)";
  if (s >= 65) return "hsl(43 96% 56%)";
  return "hsl(25 95% 55%)";
}

function leverageColor(l: number): string {
  if (l >= 10) return "hsl(0 72% 51%)";
  if (l >= 7)  return "hsl(25 95% 55%)";
  if (l >= 5)  return "hsl(43 96% 56%)";
  return "hsl(158 64% 48%)";
}

function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const c = () => setM(window.innerWidth < 768);
    c(); window.addEventListener("resize", c);
    return () => window.removeEventListener("resize", c);
  }, []);
  return m;
}

// ─── Pump Card ────────────────────────────────────────────────────────────────

function PumpCard({ sig, idx, expanded, onToggle }: {
  sig: PumpSignal; idx: number;
  expanded: boolean; onToggle: () => void;
}) {
  const isPump    = sig.type === "Pump";
  const lev       = sig.leverage || 1;
  const posUsdt   = sig.position_usdt || 0;
  const posWithLev = posUsdt * lev;

  function profitLine(pct: number): string {
    const p = posWithLev * pct / 100;
    return `+$${p.toFixed(2)}`;
  }

  return (
    <div
      className="rounded-lg border fade-in overflow-hidden"
      style={{
        animationDelay: `${idx * 0.04}s`,
        background: isPump
          ? "linear-gradient(160deg, hsl(158 64% 48% / 0.07) 0%, hsl(220 13% 10%) 50%)"
          : "linear-gradient(160deg, hsl(0 72% 51% / 0.07) 0%, hsl(220 13% 10%) 50%)",
        borderColor: isPump ? "hsl(158 64% 48% / 0.3)" : "hsl(0 72% 51% / 0.3)",
      }}
    >
      {/* ── HEADER ── */}
      <div className="flex items-start justify-between p-3 cursor-pointer" onClick={onToggle}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xl">{isPump ? "🚀" : "💣"}</span>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono font-bold text-base">{sig.pair}</span>
              <span className="text-xs font-mono px-1.5 py-0.5 rounded font-bold"
                style={{ background: isPump ? "hsl(158 64% 48% / 0.15)" : "hsl(0 72% 51% / 0.15)",
                         color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
                {isPump ? "PUMP" : "DUMP"}
              </span>
              {/* Score badge */}
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full border"
                style={{ color: scoreColor(sig.score), borderColor: scoreColor(sig.score) + "55",
                         background: scoreColor(sig.score) + "15" }}>
                {sig.score}/100
              </span>
              {/* Leverage badge */}
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded"
                style={{ color: leverageColor(lev),
                         background: leverageColor(lev) + "20",
                         border: `1px solid ${leverageColor(lev)}50` }}>
                {lev}x
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground font-mono">
              <span>{sig.exchange}</span>
              <span>·</span>
              <span>{sig.timeframe}</span>
              <span>·</span>
              <span>{sig.date || sig.time}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {sig.result && (
            <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${sig.result === "win" ? "badge-bull" : "badge-bear"}`}>
              {sig.result === "win" ? "✓ WIN" : "✗ LOSS"}
              {sig.result_pct !== undefined && ` ${sig.result_pct > 0 ? "+" : ""}${sig.result_pct}%`}
            </span>
          )}
          <Icon name={expanded ? "ChevronUp" : "ChevronDown"} size={16} className="text-muted-foreground" />
        </div>
      </div>

      {/* ── PRICE + ENTRY ROW (всегда виден) ── */}
      <div className="px-3 pb-2 flex flex-wrap gap-3">
        {/* Движение цены */}
        <div className="flex items-center gap-1.5 text-sm font-mono">
          <span className="text-muted-foreground text-xs">Цена:</span>
          <span>${fp(sig.price_from)}</span>
          <span className="text-muted-foreground">→</span>
          <span className="font-bold" style={{ color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
            ${fp(sig.price_now)}
          </span>
          <span className="text-xs font-bold px-1.5 py-0.5 rounded"
            style={{ background: isPump ? "hsl(158 64% 48% / 0.12)" : "hsl(0 72% 51% / 0.12)",
                     color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
            {isPump ? "+" : ""}{sig.pct_3 || sig.price_pct}%
          </span>
        </div>
        {/* RVOL */}
        {sig.rvol !== undefined && (
          <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground">
            <span>RVOL</span>
            <span className="font-bold" style={{ color: "hsl(43 96% 56%)" }}>{sig.rvol.toFixed(1)}x</span>
          </div>
        )}
        {/* RSI */}
        {sig.rsi !== undefined && (
          <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground">
            <span>RSI</span>
            <span className="font-bold text-foreground">{sig.rsi}</span>
          </div>
        )}
      </div>

      {/* ── ENTRY/TP/SL блок (всегда виден) ── */}
      {(sig.entry || sig.tp1) && (
        <div className="mx-3 mb-2 rounded border border-border/40 overflow-hidden"
          style={{ background: "hsl(220 13% 7%)" }}>
          {/* Вход */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border/30">
            <div className="flex items-center gap-2">
              <span className="text-sm">📌</span>
              <span className="font-mono text-xs font-bold" style={{ color: "hsl(43 96% 56%)" }}>
                {isPump ? "ВХОД LONG" : "ВХОД SHORT"}
              </span>
              <span className="font-mono text-xs font-bold px-1.5 py-0.5 rounded"
                style={{ color: leverageColor(lev), background: leverageColor(lev) + "20" }}>
                × {lev}
              </span>
            </div>
            <div className="text-right">
              <div className="font-mono font-bold text-sm" style={{ color: "hsl(43 96% 56%)" }}>
                ${fp(sig.entry)}
              </div>
              {posUsdt > 0 && (
                <div className="text-xs text-muted-foreground font-mono">
                  ${posUsdt.toFixed(0)} → <span style={{ color: "hsl(43 96% 56%)" }}>${posWithLev.toFixed(0)}</span>
                </div>
              )}
            </div>
          </div>
          {/* TP уровни */}
          {[
            { label: "TP1 — осторожный",  val: sig.tp1, pct: sig.tp1_pct },
            { label: "TP2 — оптимальный", val: sig.tp2, pct: sig.tp2_pct },
            { label: "TP3 — агрессивный", val: sig.tp3, pct: sig.tp3_pct },
          ].filter(t => t.val).map((t, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-1.5 border-b border-border/20">
              <div className="flex items-center gap-2">
                <span className="text-xs">✅</span>
                <span className="font-mono text-xs text-muted-foreground">{t.label}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-bold bull">${fp(t.val!)}</span>
                {t.pct !== undefined && (
                  <span className="font-mono text-xs bull opacity-80">
                    +{t.pct.toFixed(1)}% · <span className="text-green-400">{profitLine(t.pct)}</span>
                  </span>
                )}
              </div>
            </div>
          ))}
          {/* SL */}
          {sig.sl && (
            <div className="flex items-center justify-between px-3 py-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs">🛑</span>
                <span className="font-mono text-xs text-muted-foreground">Стоп-лосс</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-bold bear">${fp(sig.sl)}</span>
                {sig.sl_pct !== undefined && (
                  <span className="font-mono text-xs bear opacity-80">
                    -{sig.sl_pct.toFixed(1)}% · <span className="text-red-400">-${(posWithLev * sig.sl_pct / 100).toFixed(2)}</span>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── SCORE BAR ── */}
      <div className="px-3 pb-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground font-mono w-12 shrink-0">Сила:</span>
        <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all"
            style={{ width: `${sig.score}%`, background: scoreColor(sig.score) }} />
        </div>
        <span className="font-mono text-xs font-bold w-12 text-right" style={{ color: scoreColor(sig.score) }}>
          {sig.score}/100
        </span>
      </div>

      {/* ── ДЕТАЛИ (по клику) ── */}
      {expanded && (
        <div className="border-t border-border/30 px-3 py-3 flex flex-col gap-3"
          style={{ background: "hsl(220 13% 8%)" }}>

          {/* Метрики */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {[
              { label: "Объём",  val: fv(sig.volume_usd), sub: "" },
              { label: "RVOL",   val: `${(sig.rvol || 1).toFixed(1)}x`, sub: "vs среднее" },
              { label: "RSI",    val: String(sig.rsi || 50), sub: "14-period" },
              { label: "Таймфрейм", val: sig.timeframe, sub: sig.exchange },
            ].map((m, i) => (
              <div key={i} className="rounded p-2" style={{ background: "hsl(220 13% 11%)" }}>
                <div className="text-xs text-muted-foreground mb-0.5">{m.label}</div>
                <div className="font-mono text-sm font-bold">{m.val}</div>
                {m.sub && <div className="text-xs text-muted-foreground">{m.sub}</div>}
              </div>
            ))}
          </div>

          {/* Движение цены */}
          <div className="rounded p-3" style={{ background: "hsl(220 13% 11%)" }}>
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Движение цены</div>
            <div className="flex flex-wrap gap-3">
              {[
                { label: "15м", val: sig.pct_1 },
                { label: "45м", val: sig.pct_3 },
                { label: "90м", val: sig.pct_6 },
              ].filter(x => x.val !== undefined).map((x, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground font-mono">{x.label}:</span>
                  <span className={`font-mono text-sm font-bold ${(x.val || 0) >= 0 ? "bull" : "bear"}`}>
                    {(x.val || 0) >= 0 ? "+" : ""}{(x.val || 0).toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Почему дан сигнал */}
          {sig.factors && sig.factors.length > 0 && (
            <div className="rounded p-3 border" style={{ background: "hsl(220 13% 11%)", borderColor: "hsl(220 13% 18%)" }}>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Icon name="Info" size={11} />
                Почему дан сигнал
              </div>
              <div className="flex flex-col gap-1.5">
                {sig.factors.map((f, i) => (
                  <div key={i} className="text-xs font-mono text-foreground flex items-start gap-1.5">
                    <span className="text-muted-foreground shrink-0">•</span>
                    <span>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Позиция */}
          {sig.position_usdt !== undefined && sig.position_usdt > 0 && (
            <div className="rounded p-3" style={{ background: "hsl(220 13% 11%)" }}>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Позиция (виртуальный банк $1000)</div>
              <div className="flex flex-wrap gap-4 text-sm font-mono">
                <div>
                  <span className="text-muted-foreground text-xs">Своих денег: </span>
                  <span className="font-bold">${sig.position_usdt.toFixed(0)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground text-xs">Плечо: </span>
                  <span className="font-bold" style={{ color: leverageColor(lev) }}>{lev}x</span>
                </div>
                <div>
                  <span className="text-muted-foreground text-xs">С плечом: </span>
                  <span className="font-bold" style={{ color: "hsl(43 96% 56%)" }}>${posWithLev.toFixed(0)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Результат */}
          {sig.result && (
            <div className={`rounded p-3 border ${sig.result === "win" ? "border-bull/30" : "border-bear/30"}`}
              style={{ background: sig.result === "win" ? "hsl(158 64% 48% / 0.06)" : "hsl(0 72% 51% / 0.06)" }}>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Результат</div>
              <div className="flex items-center gap-3 font-mono">
                <span className={`font-bold text-lg ${sig.result === "win" ? "bull" : "bear"}`}>
                  {sig.result === "win" ? "✓ WIN" : "✗ LOSS"}
                </span>
                {sig.result_pct !== undefined && (
                  <span className={`font-bold ${sig.result === "win" ? "bull" : "bear"}`}>
                    {sig.result_pct > 0 ? "+" : ""}{sig.result_pct}%
                  </span>
                )}
                {sig.pnl_usdt !== undefined && (
                  <span className={sig.pnl_usdt >= 0 ? "bull" : "bear"}>
                    {sig.pnl_usdt >= 0 ? "+" : ""}${sig.pnl_usdt.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Live Feed ────────────────────────────────────────────────────────────────

function LiveFeed({ signals, loading, onScan }: {
  signals: PumpSignal[]; loading: boolean; onScan: () => void;
}) {
  const [filter, setFilter] = useState<"Все" | "Pump" | "Dump">("Все");
  const [expanded, setExpanded] = useState<number | null>(null);
  const filtered = signals.filter(s => filter === "Все" || s.type === filter);

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">Сигналы</span>
          {loading
            ? <span className="badge-gold text-xs px-2 py-0.5 rounded-full font-mono flex items-center gap-1.5">
                <div className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />
                скан...
              </span>
            : <span className="badge-bull text-xs px-2 py-0.5 rounded-full font-mono">{signals.length}</span>
          }
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {(["Все", "Pump", "Dump"] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`text-xs px-2.5 py-1 rounded border font-mono transition-colors ${filter === f ? "border-primary text-primary bg-primary/5" : "border-border text-muted-foreground hover:border-foreground"}`}>
                {f}
              </button>
            ))}
          </div>
          {loading && (
            <span className="text-xs text-muted-foreground font-mono flex items-center gap-1">
              <div className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />
              авто-скан
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          {[0,1,2].map(i => (
            <div key={i} className="rounded-lg border border-border p-4 animate-pulse" style={{ background: "hsl(220 13% 11%)" }}>
              <div className="flex gap-3 mb-3">
                <div className="w-8 h-8 bg-secondary rounded" />
                <div><div className="w-40 h-4 bg-secondary rounded mb-2" /><div className="w-24 h-3 bg-secondary rounded" /></div>
              </div>
              <div className="w-full h-16 bg-secondary rounded" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center py-16 gap-3 text-muted-foreground">
          <span className="text-5xl">🔍</span>
          <div className="text-sm font-medium">Нет активных сигналов</div>
          <div className="text-xs text-center max-w-xs opacity-60">
            Бот сканирует 150+ пар каждые 5 минут. Сигнал появится при обнаружении аномальной активности.
          </div>
          <div className="text-xs font-mono text-muted-foreground flex items-center gap-1.5 mt-1">
            <div className="w-2 h-2 rounded-full bg-bull blink" />
            Авто-скан каждые 5 минут
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((s, i) => (
            <PumpCard key={s.id || i} sig={s} idx={i}
              expanded={expanded === i} onToggle={() => setExpanded(expanded === i ? null : i)} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── History ─────────────────────────────────────────────────────────────────

function History() {
  const [signals, setSignals] = useState<PumpSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${API_SIGNALS}?action=saved&limit=100`)
      .then(r => r.json())
      .then(d => { setSignals(d.signals || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">История сигналов</span>
        <span className="text-xs text-muted-foreground font-mono">{signals.length} записей</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : signals.length === 0 ? (
        <div className="flex flex-col items-center py-16 gap-2 text-muted-foreground">
          <span className="text-3xl">📊</span>
          <span className="text-sm">История пуста — сигналы появятся после первых пампов</span>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {signals.map((s, i) => (
            <PumpCard key={s.id || i} sig={s} idx={i}
              expanded={expanded === i} onToggle={() => setExpanded(expanded === i ? null : i)} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Statistics ───────────────────────────────────────────────────────────────

function StatsSection() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetch(`${API_SIGNALS}?action=stats`)
      .then(r => r.json())
      .then(d => { setStats(d.stats); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!stats) return <div className="text-sm text-muted-foreground text-center py-8">Нет данных</div>;

  const p = stats.portfolio || {};
  const pnlPositive = (p.pnl || 0) >= 0;

  return (
    <div className="flex flex-col gap-4 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Статистика</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground font-mono">Только реальные закрытые сделки</span>
          <button onClick={load} className="p-1 rounded border border-border text-muted-foreground hover:text-foreground transition-colors">
            <Icon name="RefreshCw" size={11} />
          </button>
        </div>
      </div>

      {/* Портфель — главная карточка */}
      <div className="rounded-lg p-4 border"
        style={{
          background: pnlPositive
            ? "linear-gradient(135deg, hsl(158 64% 48% / 0.1), hsl(220 13% 11%))"
            : "linear-gradient(135deg, hsl(0 72% 51% / 0.1), hsl(220 13% 11%))",
          borderColor: pnlPositive ? "hsl(158 64% 48% / 0.3)" : "hsl(0 72% 51% / 0.3)",
        }}>
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider">
            Виртуальный банк · старт ${p.initial?.toFixed(0) || "1,000"} · {p.started || "—"}
          </div>
          <div className="text-xs font-mono text-muted-foreground">Результаты реальных сигналов</div>
        </div>
        <div className="flex flex-wrap gap-6 items-end">
          <div>
            <div className="font-mono text-4xl font-bold" style={{ color: pnlPositive ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
              ${p.balance?.toFixed(2) || "1000.00"}
            </div>
            <div className={`text-sm font-mono mt-1 flex items-center gap-2 ${pnlPositive ? "bull" : "bear"}`}>
              <span>{pnlPositive ? "+" : ""}${p.pnl?.toFixed(2) || "0.00"}</span>
              <span className="opacity-70">({pnlPositive ? "+" : ""}{p.pnl_pct?.toFixed(2) || "0.00"}%)</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="font-mono text-2xl font-bold bull">{p.wins || 0}</div>
              <div className="text-xs text-muted-foreground">Прибыльных</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold bear">{p.losses || 0}</div>
              <div className="text-xs text-muted-foreground">Убыточных</div>
            </div>
            <div>
              <div className={`font-mono text-2xl font-bold ${stats.win_rate >= 55 ? "bull" : stats.win_rate >= 45 ? "" : "bear"}`}>
                {stats.win_rate}%
              </div>
              <div className="text-xs text-muted-foreground">Win Rate</div>
            </div>
          </div>
        </div>
        {/* Честная подпись */}
        <div className="mt-3 text-xs text-muted-foreground border-t border-border/30 pt-3 flex items-start gap-1.5">
          <Icon name="Info" size={11} className="shrink-0 mt-0.5" />
          <span>
            Win Rate считается только по <strong className="text-foreground">закрытым</strong> сигналам (TP/SL/timeout).
            Активные сигналы в статистику не включены до закрытия.
          </span>
        </div>
      </div>

      {/* Сетка метрик */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: "Всего сигналов", val: stats.total,    sub: "за всё время",        cls: "" },
          { label: "Закрытых",       val: stats.closed,   sub: "с результатом",       cls: "" },
          { label: "Активных",       val: stats.active,   sub: "в процессе (4ч)",     cls: "gold" },
          { label: "Avg Score",      val: `${stats.avg_score}/100`, sub: "качество фильтра", cls: "" },
        ].map((m, i) => (
          <div key={i} className="panel rounded p-3">
            <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
            <div className={`font-mono text-xl font-bold ${m.cls}`}>{m.val}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* Pump vs Dump + доходность */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: "Pump-сигналы",  val: stats.pumps, sub: "рост цены + объём", cls: "bull" },
          { label: "Dump-сигналы",  val: stats.dumps, sub: "падение + объём",   cls: "bear" },
          { label: "Avg Win",       val: `+${stats.avg_win_pct}%`, sub: "средняя прибыль", cls: "bull" },
          { label: "Avg Loss",      val: `${stats.avg_loss_pct}%`, sub: "средний убыток",  cls: "bear" },
        ].map((m, i) => (
          <div key={i} className="panel rounded p-3">
            <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
            <div className={`font-mono text-xl font-bold ${m.cls}`}>{m.val}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* По биржам */}
      {stats.by_exchange?.length > 0 && (
        <div className="panel rounded p-4">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">По биржам</div>
          <div className="flex flex-col gap-3">
            {stats.by_exchange.map((e: any, i: number) => {
              const wr = e.wins + e.losses > 0 ? Math.round(e.wins / (e.wins + e.losses) * 100) : null;
              return (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-16 text-xs font-mono font-semibold">{e.exchange}</div>
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full"
                      style={{
                        width: `${stats.total > 0 ? (e.total/stats.total)*100 : 0}%`,
                        background: "hsl(158 64% 48% / 0.7)"
                      }} />
                  </div>
                  <div className="text-xs font-mono text-muted-foreground w-16 text-right">{e.total}</div>
                  {wr !== null && (
                    <div className={`text-xs font-mono w-12 text-right font-bold ${wr >= 55 ? "bull" : wr >= 45 ? "" : "bear"}`}>
                      {wr}%W
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* График активности + win/loss */}
      {stats.daily?.length > 0 && (
        <div className="panel rounded p-4">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Активность — 30 дней</div>
          <div className="flex items-end gap-0.5 h-28">
            {[...stats.daily].reverse().slice(0, 30).map((d: any, i: number) => {
              const max = Math.max(...stats.daily.map((x: any) => x.count), 1);
              const h   = Math.max((d.count / max) * 100, 3);
              const wr  = d.count > 0 && d.wins !== undefined ? Math.round(d.wins / d.count * 100) : 50;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5" title={`${d.date}: ${d.count} сигналов`}>
                  <div className="w-full rounded-t" style={{
                    height: `${h}%`,
                    background: wr >= 55 ? "hsl(158 64% 48% / 0.7)" : wr >= 40 ? "hsl(43 96% 56% / 0.7)" : "hsl(0 72% 51% / 0.7)"
                  }} />
                  {i % 5 === 0 && (
                    <div className="text-[8px] font-mono text-muted-foreground leading-none">{d.date?.slice(5)}</div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-sm" style={{background:"hsl(158 64% 48%)"}}/> ≥55% Win</div>
            <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-sm" style={{background:"hsl(43 96% 56%)"}}/> 40–55%</div>
            <div className="flex items-center gap-1"><div className="w-2 h-2 rounded-sm" style={{background:"hsl(0 72% 51%)"}}/> &lt;40% Win</div>
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <div className="rounded-lg p-3 border border-border/40 text-xs text-muted-foreground"
        style={{ background: "hsl(220 13% 8%)" }}>
        <div className="flex items-start gap-2">
          <Icon name="AlertTriangle" size={13} className="shrink-0 mt-0.5 text-gold" />
          <span>
            <strong className="text-foreground">Важно:</strong> Виртуальный банк не связан с реальными деньгами.
            Статистика отражает результаты алгоритма на исторических данных.
            Прошлые результаты не гарантируют будущую доходность.
            Торгуйте только суммами, которые готовы потерять.
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Telegram ─────────────────────────────────────────────────────────────────

function TelegramSection() {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const test = async () => {
    setTesting(true); setResult(null);
    try {
      const r = await fetch(`${API_SIGNALS}?action=test_telegram`);
      const d = await r.json();
      setResult(d.ok ? "✅ Тест отправлен!" : "❌ Ошибка: " + (d.error || ""));
    } catch { setResult("❌ Нет соединения"); }
    setTesting(false);
  };

  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Telegram уведомления</span>

      <div className="panel rounded p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">📱</span>
          <div>
            <div className="font-medium text-sm">Уведомления о пампах 24/7</div>
            <div className="text-xs text-muted-foreground">Бот торгует 24/7 независимо от того, открыт сайт или нет</div>
          </div>
        </div>

        <div className="text-xs font-mono bg-secondary/30 rounded p-3 leading-relaxed border border-border">
          <div className="text-muted-foreground mb-2 font-sans font-semibold">Пример сигнала в Telegram:</div>
          🚀 <b>PUMP — SOL/USDT</b>  [Binance]<br/>
          🟢🟢 Score: <b>82/100</b> · 15m · 14:23 UTC<br/>
          ━━━━━━━━━━━━━━━━━━━━━━━<br/>
          💰 Цена: $145.20 → <b>$151.80</b> (<b>+4.54%</b> / 45м)<br/>
          📊 Объём: <b>$3.2M</b> · RVOL <b>4.2x</b> · RSI <b>68</b><br/><br/>
          <b>━ ПОЧЕМУ СИГНАЛ ━</b><br/>
          • 💥 RVOL 4.2x — экстремальный объём<br/>
          • 🚀 Цена +4.54% за 45 мин<br/>
          • ⚡ Ускорение: нарастает<br/>
          • 📊 RSI 68 — зона роста<br/><br/>
          🎯 <b>СИГНАЛ: LONG 📈</b><br/>
          📌 Вход: <b>$151.80</b><br/>
          🔥 Плечо: <b>7x</b> (позиция $80 → $560)<br/><br/>
          ✅ TP1: <b>$153.80</b>  +1.3%  → <b>+$7.28</b><br/>
          ✅ TP2: <b>$156.90</b>  +3.4%  → <b>+$19.04</b><br/>
          ✅ TP3: <b>$161.40</b>  +6.3%  → <b>+$35.28</b><br/>
          🛑 SL: <b>$149.50</b>  -1.5%  → <b>-$8.40</b>
        </div>

        <button onClick={test} disabled={testing}
          className="flex items-center justify-center gap-2 py-2.5 rounded border border-primary text-primary hover:bg-primary/10 transition-colors disabled:opacity-40 text-sm font-mono">
          {testing ? <div className="w-4 h-4 border border-current border-t-transparent rounded-full animate-spin" /> : <Icon name="Send" size={14} />}
          {testing ? "Отправляю..." : "Тест Telegram"}
        </button>

        {result && (
          <div className="text-xs font-mono text-center" style={{ color: result.startsWith("✅") ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
            {result}
          </div>
        )}

        <div className="border-t border-border pt-3 text-xs text-muted-foreground flex flex-col gap-1.5">
          <div className="font-medium text-foreground">Настройка:</div>
          <div>1. Создайте бота через <code className="bg-secondary px-1 rounded">@BotFather</code> → получите токен</div>
          <div>2. Добавьте <code className="bg-secondary px-1 rounded">TELEGRAM_BOT_TOKEN</code> в Секреты</div>
          <div>3. Добавьте <code className="bg-secondary px-1 rounded">TELEGRAM_CHAT_ID</code> (ваш ID из <code className="bg-secondary px-1 rounded">@userinfobot</code>)</div>
        </div>
      </div>
    </div>
  );
}

// ─── MEXC Bot Section ─────────────────────────────────────────────────────────

function BotSection() {
  const [stats, setStats]         = useState<any>(null);
  const [loading, setLoading]     = useState(true);
  const [acting, setActing]       = useState(false);
  const [log, setLog]             = useState<string[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [saving, setSaving]       = useState(false);
  // Форма настроек
  const [cfgLeverage,  setCfgLeverage]  = useState(10);
  const [cfgPosPct,    setCfgPosPct]    = useState(15);   // %
  const [cfgMaxOpen,   setCfgMaxOpen]   = useState(3);
  const [cfgMinScore,  setCfgMinScore]  = useState(70);

  const addLog = (msg: string) => setLog(prev => [`[${new Date().toLocaleTimeString("ru")}] ${msg}`, ...prev.slice(0, 29)]);

  const applySettings = (d: any) => {
    setCfgLeverage(d.leverage  ?? 10);
    setCfgPosPct(Math.round((d.pos_pct ?? 0.15) * 100));
    setCfgMaxOpen(d.max_open   ?? 3);
    setCfgMinScore(d.min_score ?? 70);
  };

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_MEXC_BOT}?action=stats`);
      const d = await r.json();
      setStats(d);
      applySettings(d);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleStart = async () => {
    setActing(true);
    addLog("Запускаю бот...");
    try {
      const r = await fetch(`${API_MEXC_BOT}?action=start`);
      const d = await r.json();
      if (d.ok) {
        addLog(`✅ Бот запущен! Баланс MEXC: $${d.balance?.toFixed(2)}`);
        await load();
      } else {
        addLog(`❌ Ошибка запуска: ${d.error || "неизвестно"}`);
      }
    } catch (e) { addLog("❌ Нет соединения с сервером"); }
    setActing(false);
  };

  const handleStop = async () => {
    setActing(true);
    addLog("Останавливаю бот...");
    try {
      const r = await fetch(`${API_MEXC_BOT}?action=stop`);
      const d = await r.json();
      addLog(`🔴 Бот остановлен. Закрыто позиций: ${d.closed || 0}`);
      await load();
    } catch (e) { addLog("❌ Нет соединения с сервером"); }
    setActing(false);
  };

  const handlePing = async () => {
    setActing(true);
    addLog("Проверяю подключение к MEXC...");
    try {
      const r = await fetch(`${API_MEXC_BOT}?action=ping`);
      const d = await r.json();
      if (d.balance !== undefined) {
        addLog(`✅ MEXC подключён! Баланс фьючерсов: $${d.balance?.toFixed(2)} USDT`);
        if (d.btc_price) addLog(`✅ BTC цена: $${d.btc_price?.toLocaleString("en-US", {maximumFractionDigits:0})}`);
      } else {
        addLog(`❌ Ошибка: ${d.error || JSON.stringify(d).slice(0,150)}`);
      }
    } catch (e) { addLog("❌ Нет соединения"); }
    setActing(false);
  };

  const handleTest = async () => {
    setActing(true);
    addLog("🧪 Запускаю тестовую сделку BTC_USDT (1 контракт)...");
    try {
      const r = await fetch(`${API_MEXC_BOT}?action=test`);
      const d = await r.json();
      (d.log as string[] || []).forEach((l: string) => addLog(l));
      addLog(d.ok ? "✅ Тест прошёл успешно!" : "❌ Тест не прошёл — смотри лог");
      await load();
    } catch (e) { addLog("❌ Нет соединения"); }
    setActing(false);
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const body = {
        leverage:  cfgLeverage,
        pos_pct:   cfgPosPct / 100,
        max_open:  cfgMaxOpen,
        min_score: cfgMinScore,
      };
      const r = await fetch(`${API_MEXC_BOT}?action=settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (d.ok) {
        // Сразу применяем ответ сервера — не ждём load()
        applySettings(d);
        setStats((prev: any) => prev ? {
          ...prev,
          leverage:  d.leverage,
          pos_pct:   d.pos_pct,
          max_open:  d.max_open,
          min_score: d.min_score,
        } : prev);
        addLog(`✅ Настройки сохранены: плечо ${d.leverage}x, ${Math.round(d.pos_pct*100)}% депозита, макс ${d.max_open} позиций, score ≥${d.min_score}`);
        setShowSettings(false);
      } else {
        addLog(`❌ Ошибка сохранения настроек`);
      }
    } catch { addLog("❌ Нет соединения"); }
    setSaving(false);
  };

  const isRunning  = stats?.running || false;
  const openTrades = stats?.open_trades || [];
  const history    = stats?.history || [];
  const closed     = stats?.closed || 0;
  const wr         = stats?.win_rate || 0;

  return (
    <div className="flex flex-col gap-4 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">MEXC Авто-Бот</span>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSettings(s => !s)}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors font-mono ${showSettings ? "border-primary text-primary bg-primary/5" : "border-border text-muted-foreground hover:text-foreground"}`}>
            <Icon name="Settings2" size={12} />
            Настройки
          </button>
          <button onClick={load} className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground transition-colors">
            <Icon name="RefreshCw" size={11} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* ─── Форма настроек ─── */}
      {showSettings && (
        <div className="rounded-lg border p-4 flex flex-col gap-4"
          style={{ background: "hsl(220 13% 10%)", borderColor: "hsl(220 13% 22%)" }}>
          <div className="text-xs font-semibold text-foreground flex items-center gap-2">
            <Icon name="Settings2" size={13} />
            Параметры торговли
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Плечо */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">Плечо (leverage)</label>
              <div className="flex items-center gap-2">
                <input type="range" min={1} max={100} step={1}
                  value={cfgLeverage}
                  onChange={e => setCfgLeverage(Number(e.target.value))}
                  className="flex-1 accent-primary h-1.5 rounded cursor-pointer" />
                <span className="font-mono font-bold text-sm w-10 text-right">{cfgLeverage}x</span>
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>1x</span><span>25x</span><span>50x</span><span>100x</span>
              </div>
            </div>

            {/* % депозита */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">% депозита на сделку</label>
              <div className="flex items-center gap-2">
                <input type="range" min={1} max={50} step={1}
                  value={cfgPosPct}
                  onChange={e => setCfgPosPct(Number(e.target.value))}
                  className="flex-1 accent-primary h-1.5 rounded cursor-pointer" />
                <span className="font-mono font-bold text-sm w-10 text-right">{cfgPosPct}%</span>
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>1%</span><span>10%</span><span>25%</span><span>50%</span>
              </div>
            </div>

            {/* Макс позиций */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">Макс. одновременных позиций</label>
              <div className="flex gap-1.5 flex-wrap">
                {[1,2,3,4,5,6].map(n => (
                  <button key={n} onClick={() => setCfgMaxOpen(n)}
                    className={`px-3 py-1.5 rounded text-xs font-mono font-bold border transition-colors ${cfgMaxOpen === n ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:border-foreground"}`}>
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* Мин. score */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">Мин. score сигнала</label>
              <div className="flex gap-1.5 flex-wrap">
                {[50,55,60,65,70,75,80,85].map(n => (
                  <button key={n} onClick={() => setCfgMinScore(n)}
                    className={`px-2.5 py-1.5 rounded text-xs font-mono font-bold border transition-colors ${cfgMinScore === n ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:border-foreground"}`}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Превью настроек */}
          <div className="rounded p-3 text-xs font-mono flex flex-wrap gap-4"
            style={{ background: "hsl(220 13% 7%)" }}>
            {stats?.balance > 0 && (
              <span className="text-muted-foreground">
                На сделку: <span className="text-foreground font-bold">
                  ${(stats.balance * cfgPosPct / 100).toFixed(0)} USDT
                  → экспозиция ${(stats.balance * cfgPosPct / 100 * cfgLeverage).toFixed(0)} USDT
                </span>
              </span>
            )}
            <span className="text-muted-foreground">
              Риск/сделку: <span className={`font-bold ${cfgPosPct * cfgLeverage > 100 ? "bear" : cfgPosPct * cfgLeverage > 50 ? "text-yellow-400" : "bull"}`}>
                {cfgPosPct}% × {cfgLeverage}x = {cfgPosPct * cfgLeverage}% баланса
              </span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={handleSaveSettings} disabled={saving}
              className="flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all disabled:opacity-50"
              style={{ background: "hsl(158 64% 48%)", color: "hsl(220 13% 8%)" }}>
              {saving
                ? <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                : <Icon name="Save" size={14} />}
              Сохранить
            </button>
            <button onClick={() => setShowSettings(false)}
              className="px-4 py-2 rounded-lg text-sm border border-border text-muted-foreground hover:text-foreground transition-colors">
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Главная кнопка запуска */}
      <div className="rounded-lg border p-5 flex flex-col gap-4"
        style={{
          background: isRunning
            ? "linear-gradient(135deg, hsl(158 64% 48% / 0.12), hsl(220 13% 11%))"
            : "linear-gradient(135deg, hsl(220 13% 13%), hsl(220 13% 11%))",
          borderColor: isRunning ? "hsl(158 64% 48% / 0.4)" : "hsl(220 13% 20%)",
        }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${isRunning ? "bg-bull blink" : "bg-muted-foreground"}`} />
            <div>
              <div className="font-semibold text-sm">
                {isRunning ? "Бот работает 🟢" : "Бот остановлен 🔴"}
              </div>
              <div className="text-xs text-muted-foreground font-mono">
                MEXC Futures · {stats?.leverage ?? 10}x · {Math.round((stats?.pos_pct ?? 0.15) * 100)}% депозита · до {stats?.max_open ?? 3} позиций
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={handlePing} disabled={acting}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border border-border transition-all disabled:opacity-40 font-mono text-muted-foreground hover:text-foreground">
              {acting ? <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" /> : <Icon name="Wifi" size={13} />}
              Пинг
            </button>
            <button onClick={handleTest} disabled={acting}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border border-border transition-all disabled:opacity-40 font-mono"
              style={{ borderColor: "hsl(43 96% 56% / 0.5)", color: "hsl(43 96% 56%)" }}>
              {acting ? <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" /> : <Icon name="FlaskConical" size={13} />}
              Тест сделка
            </button>
            {isRunning ? (
              <button onClick={handleStop} disabled={acting}
                className="flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all disabled:opacity-40"
                style={{ background: "hsl(0 72% 51%)", color: "white" }}>
                {acting ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Icon name="Square" size={14} />}
                Остановить
              </button>
            ) : (
              <button onClick={handleStart} disabled={acting}
                className="flex items-center gap-2 px-5 py-2 rounded-lg font-semibold text-sm transition-all disabled:opacity-40"
                style={{ background: "hsl(158 64% 48%)", color: "hsl(220 13% 8%)" }}>
                {acting ? <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> : <Icon name="Play" size={14} />}
                Запустить бот
              </button>
            )}
          </div>
        </div>

        {/* Параметры бота — реальные значения */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Биржа",       val: "MEXC Futures" },
            { label: "Плечо",       val: `${stats?.leverage ?? 10}x` },
            { label: "На сделку",   val: `${Math.round((stats?.pos_pct ?? 0.15) * 100)}% депозита` },
            { label: "Макс позиций",val: `${stats?.max_open ?? 3} одновременно` },
          ].map((m, i) => (
            <div key={i} className="rounded p-2 text-center" style={{ background: "hsl(220 13% 8%)" }}>
              <div className="text-xs text-muted-foreground">{m.label}</div>
              <div className="font-mono text-sm font-bold mt-0.5">{m.val}</div>
            </div>
          ))}
        </div>

        {/* Баланс */}
        <div className="border-t border-border/30 pt-3 flex items-center justify-between text-sm font-mono">
          <span className="text-muted-foreground">Баланс MEXC Futures:</span>
          {(stats?.balance || 0) > 0.01
            ? <span className="font-bold bull">${(stats?.balance || 0).toFixed(2)} USDT</span>
            : <span className="text-xs font-mono bear flex items-center gap-1.5">
                <Icon name="AlertTriangle" size={12} />
                Пустой — нужно пополнить
              </span>
          }
        </div>

        {/* Инструкция пополнения */}
        {(stats?.balance || 0) < 1 && (
          <div className="rounded-lg p-3 border text-xs"
            style={{ background: "hsl(43 96% 56% / 0.05)", borderColor: "hsl(43 96% 56% / 0.3)" }}>
            <div className="flex items-start gap-2">
              <Icon name="AlertTriangle" size={13} className="shrink-0 mt-0.5" style={{ color: "hsl(43 96% 56%)" }} />
              <div className="flex flex-col gap-1">
                <span className="font-semibold" style={{ color: "hsl(43 96% 56%)" }}>Нужно пополнить фьючерсный счёт MEXC</span>
                <span className="text-muted-foreground">Сейчас на фьючерсном счёте пусто — бот не сможет открывать сделки.</span>
                <div className="mt-1 flex flex-col gap-0.5 text-foreground">
                  <div>1. Войди на <strong>mexc.com</strong></div>
                  <div>2. Активы → <strong>Перевод средств</strong></div>
                  <div>3. Откуда: Спот → Куда: <strong>Фьючерсы</strong></div>
                  <div>4. Сумма: минимум <strong>$20–50 USDT</strong></div>
                  <div>5. Нажми «Тест сделка» — убедись что всё ОК</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Статистика */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Всего сделок", val: stats.total || 0,       cls: "" },
            { label: "Прибыльных",   val: stats.wins || 0,        cls: "bull" },
            { label: "Убыточных",    val: stats.losses || 0,      cls: "bear" },
            { label: "Win Rate",     val: `${wr}%`,               cls: wr >= 55 ? "bull" : wr >= 45 ? "" : "bear" },
          ].map((m, i) => (
            <div key={i} className="panel rounded p-3 text-center">
              <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
              <div className={`font-mono text-2xl font-bold ${m.cls}`}>{m.val}</div>
            </div>
          ))}
        </div>
      )}

      {/* P&L */}
      {closed > 0 && (
        <div className="panel rounded p-3 flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Итого P&L (закрытые сделки):</span>
          <span className={`font-mono font-bold text-lg ${(stats?.total_pnl || 0) >= 0 ? "bull" : "bear"}`}>
            {(stats?.total_pnl || 0) >= 0 ? "+" : ""}${(stats?.total_pnl || 0).toFixed(2)} USDT
          </span>
        </div>
      )}

      {/* Открытые позиции */}
      {openTrades.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-bull blink" />
            Открытые позиции ({openTrades.length})
          </div>
          <div className="flex flex-col gap-2">
            {openTrades.map((t: any, i: number) => (
              <div key={i} className="rounded border border-border/40 p-2.5 flex flex-wrap items-center justify-between gap-2"
                style={{ background: "hsl(220 13% 9%)" }}>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm">{t.pair}</span>
                    <span className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded ${t.direction === "LONG" ? "badge-bull" : "badge-bear"}`}>
                      {t.direction}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">Score {t.score}/100</span>
                  </div>
                  <div className="text-xs text-muted-foreground font-mono mt-0.5">
                    Открыта: {t.opened} · Позиция: ${t.pos?.toFixed(0)} × 10x
                  </div>
                </div>
                <div className="text-right text-xs font-mono">
                  <div className="text-muted-foreground">Вход ${t.entry?.toFixed ? t.entry.toFixed(4) : t.entry}</div>
                  <div className="bull">TP2 ${t.tp2?.toFixed ? t.tp2.toFixed(4) : t.tp2}</div>
                  <div className="bear">SL ${t.sl?.toFixed ? t.sl.toFixed(4) : t.sl}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* История сделок */}
      {history.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">История сделок</div>
          <div className="flex flex-col gap-1.5">
            {history.map((t: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-xs font-mono py-1.5 px-2 rounded"
                style={{ background: "hsl(220 13% 9%)" }}>
                <div className="flex items-center gap-2">
                  <span className={t.pnl >= 0 ? "bull" : "bear"}>{t.pnl >= 0 ? "✓" : "✗"}</span>
                  <span className="font-bold">{t.pair}</span>
                  <span className="text-muted-foreground">{t.direction}</span>
                  <span className="text-muted-foreground hidden md:inline">{t.reason}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={t.pnl >= 0 ? "bull" : "bear"}>
                    {t.pnl >= 0 ? "+" : ""}${t.pnl?.toFixed(2)}
                  </span>
                  <span className="text-muted-foreground">{t.closed}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Лог */}
      {log.length > 0 && (
        <div className="rounded p-3 border border-border/30" style={{ background: "hsl(220 13% 7%)" }}>
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Лог</div>
          <div className="flex flex-col gap-0.5 max-h-32 overflow-y-auto">
            {log.map((l, i) => (
              <div key={i} className="text-xs font-mono text-muted-foreground">{l}</div>
            ))}
          </div>
        </div>
      )}

      {/* Как работает */}
      <div className="rounded-lg p-3 border border-border/40 text-xs text-muted-foreground"
        style={{ background: "hsl(220 13% 8%)" }}>
        <div className="font-medium text-foreground mb-2">Как работает бот:</div>
        <div className="flex flex-col gap-1">
          <div>1. Каждые 5 минут PumpBot сканирует 150+ пар на 4 биржах</div>
          <div>2. Сигнал с Score ≥ 70 → бот открывает позицию на MEXC Futures</div>
          <div>3. Вход: 15% баланса × 10x плечо (до 3 позиций одновременно)</div>
          <div>4. TP1/TP2 и SL берутся из сигнала. Таймаут — 4 часа</div>
          <div>5. Все сделки приходят в Telegram с P&L</div>
        </div>
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ signals, loading, onScan, market }: {
  signals: PumpSignal[]; loading: boolean; onScan: () => void; market: MarketPair[];
}) {
  const pumps = signals.filter(s => s.type === "Pump");
  const dumps  = signals.filter(s => s.type === "Dump");
  const btc    = market.find(p => p.symbol?.includes("BTC"));
  const topSig = signals[0];
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex flex-col gap-3 fade-in">
      {/* Метрики */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Пампов</div>
          <div className="font-mono text-2xl font-bold bull">{pumps.length}</div>
          <div className="text-xs text-muted-foreground mt-1">🚀 активных</div>
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Дампов</div>
          <div className="font-mono text-2xl font-bold bear">{dumps.length}</div>
          <div className="text-xs text-muted-foreground mt-1">💣 активных</div>
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">BTC</div>
          {btc ? (
            <>
              <div className="font-mono text-base font-semibold" style={{ color: btc.change >= 0 ? "hsl(var(--bull))" : "hsl(var(--bear))" }}>
                ${btc.price.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className={`text-xs font-mono mt-1 ${btc.change >= 0 ? "bull" : "bear"}`}>
                {btc.change >= 0 ? "+" : ""}{btc.change.toFixed(2)}%
              </div>
            </>
          ) : <div className="text-muted-foreground font-mono">...</div>}
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Скан</div>
          <div className="font-mono text-base font-semibold">150+ пар</div>
          <div className="text-xs text-muted-foreground mt-1">4 биржи · 5 мин</div>
        </div>
      </div>

      {/* Топ сигнал */}
      {topSig && (
        <div>
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Последний сигнал</div>
          <PumpCard sig={topSig} idx={0} expanded={expanded} onToggle={() => setExpanded(!expanded)} />
        </div>
      )}

      {/* Рынок */}
      {market.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Рынок</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
            {market.slice(0, 8).map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs font-mono py-1 px-2 rounded"
                style={{ background: "hsl(220 13% 9%)" }}>
                <span className="text-muted-foreground">{p.symbol?.replace("USDT", "").replace("-USDT", "")}</span>
                <span className={p.change >= 0 ? "bull" : "bear"}>{p.change >= 0 ? "+" : ""}{p.change.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Статус */}
      <div className="panel rounded p-2.5 flex flex-wrap items-center gap-4">
        {["Binance", "Bybit", "OKX", "MEXC"].map(e => (
          <div key={e} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full blink bg-bull" />
            <span className="text-xs font-mono">{e}</span>
          </div>
        ))}
        <div className="ml-auto flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
          {loading
            ? <><div className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" /> скан...</>
            : <><div className="w-2 h-2 rounded-full bg-bull blink" /> авто</>
          }
        </div>
      </div>
    </div>
  );
}

// ─── Ticker Tape ─────────────────────────────────────────────────────────────

function TickerTape({ pairs }: { pairs: MarketPair[] }) {
  if (!pairs.length) return null;
  const items = [...pairs, ...pairs];
  return (
    <div className="overflow-hidden border-b border-border shrink-0" style={{ background: "hsl(220 13% 7%)" }}>
      <div className="ticker-scroll inline-flex gap-6 py-1.5 px-4">
        {items.map((p, i) => (
          <div key={i} className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="font-mono text-xs text-muted-foreground">{p.symbol?.replace("USDT","").replace("-USDT","")}</span>
            <span className="font-mono text-xs">{p.price >= 1000 ? p.price.toLocaleString("en-US",{maximumFractionDigits:0}) : fp(p.price)}</span>
            <span className={`font-mono text-xs ${p.change >= 0 ? "bull" : "bear"}`}>{p.change >= 0 ? "▲" : "▼"}{Math.abs(p.change).toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "dashboard", label: "Дашборд",   icon: "LayoutDashboard" },
  { id: "signals",   label: "Сигналы",   icon: "Zap" },
  { id: "bot",       label: "Авто-Бот",  icon: "Bot" },
  { id: "history",   label: "История",   icon: "History" },
  { id: "stats",     label: "Статистика",icon: "BarChart2" },
  { id: "telegram",  label: "Telegram",  icon: "Bell" },
];

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function Index() {
  const [active,  setActive]  = useState("dashboard");
  const [signals, setSignals] = useState<PumpSignal[]>([]);
  const [market,  setMarket]  = useState<MarketPair[]>([]);
  const [loading, setLoading] = useState(false);
  const isMobile = useIsMobile();
  const scanRef  = useRef(false);

  const fetchMarket = useCallback(async () => {
    try {
      const r = await fetch(`${API_MARKET}?action=all`);
      const d = await r.json();
      if (d.pairs) setMarket(d.pairs);
    } catch (_e) { /* ignore */ }
  }, []);

  const scan = useCallback(async () => {
    if (scanRef.current) return;
    scanRef.current = true;
    setLoading(true);
    try {
      const r = await fetch(`${API_SIGNALS}?action=scan&exchange=Binance`);
      const d = await r.json();
      if (d.signals?.length) setSignals(prev => {
        const ids = new Set(prev.map(s => s.id));
        const news = (d.signals as PumpSignal[]).filter(s => !ids.has(s.id));
        return [...news, ...prev].slice(0, 100);
      });
    } catch (_e) { /* ignore */ }
    setLoading(false);
    scanRef.current = false;
  }, []);

  const loadSaved = useCallback(async () => {
    try {
      const r = await fetch(`${API_SIGNALS}?action=saved&limit=50`);
      const d = await r.json();
      if (d.signals?.length) setSignals(d.signals);
    } catch (_e) { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchMarket();
    loadSaved();
    scan(); // автостарт сразу при открытии
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setInterval(() => { fetchMarket(); scan(); }, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchMarket, scan]);

  const renderSection = () => {
    switch (active) {
      case "dashboard": return <Dashboard signals={signals} loading={loading} onScan={scan} market={market} />;
      case "signals":   return <LiveFeed  signals={signals} loading={loading} onScan={scan} />;
      case "bot":       return <BotSection />;
      case "history":   return <History />;
      case "stats":     return <StatsSection />;
      case "telegram":  return <TelegramSection />;
      default:          return <Dashboard signals={signals} loading={loading} onScan={scan} market={market} />;
    }
  };

  return (
    <div className={`flex flex-col ${isMobile ? "min-h-screen" : "h-screen overflow-hidden"}`}>
      {/* Header */}
      <header className="flex items-center justify-between px-3 md:px-4 py-2 border-b border-border shrink-0"
        style={{ background: "hsl(220 13% 7%)" }}>
        <div className="flex items-center gap-2">
          <span className="text-xl">🚀</span>
          <span className="font-mono font-bold text-sm">PumpBot</span>
          {!isMobile && (
            <>
              <div className="w-px h-4 bg-border mx-1" />
              <span className="text-xs text-muted-foreground font-mono">Binance · Bybit · OKX · MEXC</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 text-xs font-mono px-2 py-1 rounded border ${loading ? "border-gold/30 text-gold" : "border-bull/30 text-bull"}`}
            style={{ background: loading ? "hsl(43 96% 56% / 0.05)" : "hsl(158 64% 48% / 0.05)" }}>
            <div className={`w-1.5 h-1.5 rounded-full blink ${loading ? "bg-gold" : "bg-bull"}`} />
            {!isMobile && <span>{loading ? "сканирую..." : "24/7 активен"}</span>}
          </div>
          <button onClick={() => { fetchMarket(); scan(); }} disabled={loading}
            className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40">
            <Icon name="RefreshCw" size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <TickerTape pairs={market} />

      <div className={`flex flex-1 ${isMobile ? "flex-col" : "overflow-hidden"}`}>
        {!isMobile && (
          <aside className="w-44 border-r border-border shrink-0 flex flex-col" style={{ background: "hsl(var(--sidebar-background))" }}>
            <nav className="flex-1 py-2">
              {NAV.map(item => (
                <button key={item.id} onClick={() => setActive(item.id)}
                  className={`nav-item w-full flex items-center gap-3 px-4 py-2.5 text-left ${active === item.id ? "nav-active" : "text-sidebar-foreground"}`}>
                  <Icon name={item.icon} size={14} />
                  <span className="text-xs font-medium">{item.label}</span>
                  {item.id === "signals" && signals.length > 0 && (
                    <span className="ml-auto text-xs font-mono bg-primary text-primary-foreground rounded-full w-4 h-4 flex items-center justify-center">
                      {Math.min(signals.length, 9)}
                    </span>
                  )}
                </button>
              ))}
            </nav>
            <div className="border-t border-border p-3">
              <div className="text-xs text-muted-foreground font-mono space-y-1">
                <div className="flex justify-between"><span>Сигналов:</span><span className="text-foreground">{signals.length}</span></div>
                <div className="flex justify-between"><span>Pump:</span><span className="bull">{signals.filter(s=>s.type==="Pump").length}</span></div>
                <div className="flex justify-between"><span>Dump:</span><span className="bear">{signals.filter(s=>s.type==="Dump").length}</span></div>
                <div className="flex justify-between"><span>Банк:</span><span className="text-foreground">$1,000</span></div>
              </div>
            </div>
          </aside>
        )}

        <main className={`flex-1 overflow-y-auto p-3 md:p-4 ${isMobile ? "pb-20" : ""}`}>
          {renderSection()}
        </main>
      </div>

      {isMobile && (
        <nav className="fixed bottom-0 left-0 right-0 border-t border-border z-50 flex"
          style={{ background: "hsl(220 13% 7%)" }}>
          {NAV.map(item => (
            <button key={item.id} onClick={() => setActive(item.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-colors relative ${active === item.id ? "text-primary" : "text-muted-foreground"}`}>
              <Icon name={item.icon} size={18} />
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
              {active === item.id && <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-primary rounded-full" />}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}