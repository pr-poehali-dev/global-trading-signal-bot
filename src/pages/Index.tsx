/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useCallback, useRef } from "react";
import Icon from "@/components/ui/icon";

const API_SIGNALS = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed";
const API_MARKET = "https://functions.poehali.dev/b4830b16-e61f-4ab5-8a8b-eb323709567c";

// ─── Types ────────────────────────────────────────────────────────────────────

interface PumpSignal {
  id?: number;
  pair: string;
  symbol?: string;
  type: "Pump" | "Dump";
  exchange: string;
  price_now: number;
  price_from: number;
  price_pct: number;
  price_pct_6?: number;
  volume_usd: number;
  volume_pct: number;
  volume_increase_usd?: number;
  volume_24h?: number;
  change_24h?: number;
  strength: number;
  timeframe: string;
  time: string;
  date?: string;
  analysis?: string;
  result?: string;
  result_pct?: number;
  entry?: number;
  tp1?: number;
  tp2?: number;
  tp3?: number;
  sl?: number;
  tp1_pct?: number;
  tp2_pct?: number;
  tp3_pct?: number;
  sl_pct?: number;
}

interface MarketPair {
  symbol: string;
  price: number;
  change: number;
  volume: number;
  candles?: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtPrice(p: number): string {
  if (!p) return "—";
  if (p >= 10000) return p.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(4);
  if (p >= 0.01) return p.toFixed(6);
  return p.toFixed(8);
}

function fmtVol(v: number): string {
  if (!v) return "$0";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(2)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtVolIncrease(v: number): string {
  if (!v) return "$0";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(2)}K`;
  return `$${v.toFixed(0)}`;
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const d = new Date(dateStr.includes("T") ? dateStr : dateStr + "Z");
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return `${diff}с назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)}м назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}ч назад`;
  return `${Math.floor(diff / 86400)}д назад`;
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

function PumpCard({ sig, idx }: { sig: PumpSignal; idx: number }) {
  const isPump = sig.type === "Pump";
  const isNew = idx === 0;

  return (
    <div
      className="rounded-lg border fade-in"
      style={{
        animationDelay: `${idx * 0.05}s`,
        background: isPump
          ? "linear-gradient(135deg, hsl(158 64% 48% / 0.06) 0%, hsl(220 13% 11%) 60%)"
          : "linear-gradient(135deg, hsl(0 72% 51% / 0.06) 0%, hsl(220 13% 11%) 60%)",
        borderColor: isPump ? "hsl(158 64% 48% / 0.25)" : "hsl(0 72% 51% / 0.25)",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between p-3 pb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-lg">{isPump ? "🚀" : "📉"}</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-sm">
                {isPump ? "Pump" : "Dump"} - {sig.pair}
              </span>
              {isNew && (
                <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                  style={{ background: "hsl(43 96% 56% / 0.15)", color: "hsl(43 96% 56%)", border: "1px solid hsl(43 96% 56% / 0.3)" }}>
                  NEW
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground font-mono mt-0.5">
              {isPump ? "Pump" : "Dump"} Activity on {sig.pair}{" "}
              <span style={{ color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
                {isPump ? "🟢🟢" : "🔴🔴"}
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs font-mono text-muted-foreground">{sig.exchange}</span>
          <span className="text-xs font-mono text-muted-foreground">{sig.timeframe} · {sig.time}</span>
        </div>
      </div>

      {/* Body */}
      <div className="px-3 pb-3 flex flex-col gap-2">
        {/* Price row */}
        <div className="flex items-center gap-2 flex-wrap">
          <Icon name="DollarSign" size={13} className="text-muted-foreground shrink-0" />
          <span className="text-xs text-muted-foreground">Price:</span>
          <span className="font-mono text-sm font-semibold">${fmtPrice(sig.price_from)}</span>
          <span className="text-muted-foreground">➜</span>
          <span className="font-mono text-sm font-bold" style={{ color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)" }}>
            ${fmtPrice(sig.price_now)}
          </span>
          <span className="font-mono text-sm font-bold px-2 py-0.5 rounded"
            style={{
              background: isPump ? "hsl(158 64% 48% / 0.12)" : "hsl(0 72% 51% / 0.12)",
              color: isPump ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)",
            }}>
            ({isPump ? "+" : ""}{sig.price_pct}%)
          </span>
        </div>

        {/* Volume row */}
        <div className="flex items-center gap-2 flex-wrap">
          <Icon name="BarChart2" size={13} className="text-muted-foreground shrink-0" />
          <span className="text-xs text-muted-foreground">Volume:</span>
          <span className="font-mono text-sm font-semibold">{fmtVol(sig.volume_usd)}</span>
          <span className="font-mono text-sm font-bold" style={{ color: "hsl(158 64% 48%)" }}>
            (+{sig.volume_pct.toFixed(2)}%)
          </span>
        </div>

        {/* Volume increase */}
        {sig.volume_increase_usd !== undefined && sig.volume_increase_usd > 0 && (
          <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
            <span>Volume increased by</span>
            <span className="font-semibold" style={{ color: "hsl(158 64% 48%)" }}>
              {fmtVolIncrease(sig.volume_increase_usd)}
            </span>
            <span>⬆️</span>
          </div>
        )}

        {/* Entry / TP / SL block */}
        {(sig.entry || sig.tp1 || sig.sl) && (
          <div className="mt-1 rounded-lg overflow-hidden border border-border/50"
            style={{ background: "hsl(220 13% 8%)" }}>
            {/* Entry */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/30">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono" style={{ color: "hsl(43 96% 56%)" }}>📌</span>
                <span className="text-xs font-mono font-semibold" style={{ color: "hsl(43 96% 56%)" }}>
                  {isPump ? "ВХОД LONG" : "ВХОД SHORT"}
                </span>
              </div>
              <span className="font-mono text-sm font-bold" style={{ color: "hsl(43 96% 56%)" }}>
                ${fmtPrice(sig.entry || sig.price_now)}
              </span>
            </div>
            {/* TP levels */}
            {[
              { label: "TP1 (осторожный)", val: sig.tp1, pct: sig.tp1_pct },
              { label: "TP2 (оптимальный)", val: sig.tp2, pct: sig.tp2_pct },
              { label: "TP3 (агрессивный)", val: sig.tp3, pct: sig.tp3_pct },
            ].filter(t => t.val).map((t, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-1.5 border-b border-border/30">
                <div className="flex items-center gap-2">
                  <span className="text-xs">✅</span>
                  <span className="text-xs text-muted-foreground font-mono">{t.label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold bull">${fmtPrice(t.val!)}</span>
                  {t.pct !== undefined && (
                    <span className="text-xs font-mono bull opacity-70">(+{t.pct.toFixed(1)}%)</span>
                  )}
                </div>
              </div>
            ))}
            {/* SL */}
            {sig.sl && (
              <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs">🛑</span>
                  <span className="text-xs text-muted-foreground font-mono">Стоп-лосс</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold bear">${fmtPrice(sig.sl)}</span>
                  {sig.sl_pct !== undefined && (
                    <span className="text-xs font-mono bear opacity-70">(-{sig.sl_pct.toFixed(1)}%)</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Strength bar */}
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-muted-foreground font-mono shrink-0">Сила:</span>
          <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${sig.strength}%`,
                background: sig.strength >= 80
                  ? "hsl(158 64% 48%)"
                  : sig.strength >= 65
                    ? "hsl(43 96% 56%)"
                    : "hsl(25 95% 55%)",
              }}
            />
          </div>
          <span className="font-mono text-xs font-bold" style={{
            color: sig.strength >= 80 ? "hsl(158 64% 48%)" : sig.strength >= 65 ? "hsl(43 96% 56%)" : "hsl(25 95% 55%)"
          }}>{sig.strength}%</span>
        </div>

        {/* Result badge if closed */}
        {sig.result && (
          <div className="flex items-center gap-2">
            <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${sig.result === "win" ? "badge-bull" : "badge-bear"}`}>
              {sig.result === "win" ? "✓ WIN" : "✗ LOSS"} {sig.result_pct !== undefined ? `${sig.result_pct > 0 ? "+" : ""}${sig.result_pct}%` : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Live Feed ────────────────────────────────────────────────────────────────

function LiveFeed({ signals, loading, onScan }: { signals: PumpSignal[]; loading: boolean; onScan: () => void }) {
  const [filter, setFilter] = useState<"Все" | "Pump" | "Dump">("Все");
  const filtered = signals.filter(s => filter === "Все" || s.type === filter);

  return (
    <div className="flex flex-col gap-3 fade-in">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">Pump-сигналы</span>
          {loading
            ? <span className="badge-gold text-xs px-2 py-0.5 rounded-full font-mono flex items-center gap-1.5">
                <div className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />
                сканирую...
              </span>
            : <span className="badge-bull text-xs px-2 py-0.5 rounded-full font-mono">{signals.length} сигналов</span>
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
          <button onClick={onScan} disabled={loading}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-primary text-primary hover:bg-primary/10 transition-colors disabled:opacity-40 font-mono">
            <Icon name="RefreshCw" size={11} className={loading ? "animate-spin" : ""} />
            Сканировать
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array(3).fill(null).map((_, i) => (
            <div key={i} className="rounded-lg border border-border p-4 animate-pulse" style={{ background: "hsl(220 13% 11%)" }}>
              <div className="flex gap-3 mb-3">
                <div className="w-7 h-7 bg-secondary rounded" />
                <div className="flex-1"><div className="w-40 h-4 bg-secondary rounded mb-2" /><div className="w-24 h-3 bg-secondary rounded" /></div>
              </div>
              <div className="w-full h-3 bg-secondary rounded mb-2" />
              <div className="w-3/4 h-3 bg-secondary rounded" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
          <span className="text-4xl">🔍</span>
          <div className="text-sm font-medium">Активных pump-сигналов нет</div>
          <div className="text-xs text-center max-w-xs opacity-60">
            Бот сканирует 80+ пар каждые 5 минут. Сигнал появляется при резком росте цены (+3%+) и объёма (+30%+)
          </div>
          <button onClick={onScan} className="mt-2 text-xs px-4 py-2 rounded border border-primary text-primary hover:bg-primary/10 transition-colors font-mono">
            Запустить сканирование
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((s, i) => <PumpCard key={s.id || i} sig={s} idx={i} />)}
        </div>
      )}
    </div>
  );
}

// ─── History ──────────────────────────────────────────────────────────────────

function History() {
  const [signals, setSignals] = useState<PumpSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_SIGNALS}?action=saved&limit=100`).then(r => r.json()),
      fetch(`${API_SIGNALS}?action=stats`).then(r => r.json()),
    ]).then(([savedData, statsData]) => {
      setSignals(savedData.signals || []);
      setStats(statsData.stats || null);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">История сигналов</span>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Всего сигналов", value: stats.total, cls: "" },
            { label: "Pump", value: stats.pumps, cls: "bull" },
            { label: "Dump", value: stats.dumps, cls: "bear" },
            { label: "Win Rate", value: `${stats.win_rate}%`, cls: stats.win_rate >= 60 ? "bull" : "bear" },
          ].map((m, i) => (
            <div key={i} className="panel rounded p-3">
              <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
              <div className={`font-mono text-lg font-bold ${m.cls}`}>{m.value}</div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : signals.length === 0 ? (
        <div className="flex flex-col items-center py-16 gap-2 text-muted-foreground">
          <span className="text-3xl">📊</span>
          <span className="text-sm">История пуста — сигналы появятся после первых пампов</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {signals.map((s, i) => <PumpCard key={s.id || i} sig={s} idx={i} />)}
        </div>
      )}
    </div>
  );
}

// ─── Stats ────────────────────────────────────────────────────────────────────

function StatsSection() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_SIGNALS}?action=stats`)
      .then(r => r.json())
      .then(d => { setStats(d.stats); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!stats) return <div className="text-muted-foreground text-sm py-8 text-center">Нет данных</div>;

  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Статистика</span>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { label: "Всего сигналов", value: stats.total, sub: "за всё время", cls: "" },
          { label: "Pump-сигналов", value: stats.pumps, sub: "рост цены + объём", cls: "bull" },
          { label: "Dump-сигналов", value: stats.dumps, sub: "падение + объём", cls: "bear" },
          { label: "Win Rate", value: `${stats.win_rate}%`, sub: `${stats.wins}W / ${stats.losses}L`, cls: stats.win_rate >= 60 ? "bull" : "bear" },
          { label: "Закрытых", value: stats.closed, sub: "с результатом", cls: "" },
          { label: "В обработке", value: stats.total - stats.closed, sub: "активных", cls: "gold" },
        ].map((m, i) => (
          <div key={i} className="panel rounded p-4">
            <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
            <div className={`font-mono text-2xl font-bold ${m.cls}`}>{m.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{m.sub}</div>
          </div>
        ))}
      </div>

      {stats.daily && stats.daily.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Активность за 7 дней</div>
          <div className="flex items-end gap-1 h-20">
            {stats.daily.slice(0, 7).reverse().map((d: any, i: number) => {
              const max = Math.max(...stats.daily.slice(0, 7).map((x: any) => x.count));
              const h = max > 0 ? Math.max((d.count / max) * 100, 4) : 4;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full rounded-t" style={{ height: `${h}%`, background: "hsl(158 64% 48% / 0.5)" }} />
                  <div className="text-[9px] font-mono text-muted-foreground">{d.date?.slice(5)}</div>
                  <div className="text-[9px] font-mono text-foreground">{d.count}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Telegram Setup ───────────────────────────────────────────────────────────

function TelegramSection() {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const test = async () => {
    setTesting(true); setResult(null);
    try {
      const r = await fetch(`${API_SIGNALS}?action=test_telegram`);
      const d = await r.json();
      setResult(d.ok ? "✅ Тест отправлен в Telegram!" : "❌ Ошибка: " + (d.error || "неизвестно"));
    } catch { setResult("❌ Ошибка соединения"); }
    setTesting(false);
  };

  return (
    <div className="flex flex-col gap-3 fade-in">
      <span className="text-sm font-semibold">Telegram уведомления</span>

      <div className="panel rounded p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">📱</span>
          <div>
            <div className="font-medium text-sm">Уведомления о пампах</div>
            <div className="text-xs text-muted-foreground">Бот торгует 24/7 независимо от того, открыт сайт или нет</div>
          </div>
        </div>

        <div className="text-xs text-muted-foreground flex flex-col gap-1.5 border border-border rounded p-3">
          <div className="font-medium text-foreground mb-1">Как выглядит сигнал в Telegram:</div>
          <div className="font-mono bg-secondary/40 rounded p-2 text-xs leading-relaxed">
            🚀 <b>Pump - CHR/USDT</b><br/>
            Pump Activity on CHR/USDT 🟢🟢<br/><br/>
            💰 Price: $0.0209 ➜ $0.0225 (+7.35%)<br/>
            📊 Volume: $2.06M (+19.92%)<br/>
            Volume increased by $342.86K ⬆️<br/>
            ⏱ Timeframe: 15m | Exchange: Binance
          </div>
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

        <div className="border-t border-border pt-3 text-xs text-muted-foreground flex flex-col gap-1">
          <div className="font-medium text-foreground">Настройка:</div>
          <div>1. Создайте бота через @BotFather → получите токен</div>
          <div>2. Добавьте <code className="bg-secondary px-1 rounded">TELEGRAM_BOT_TOKEN</code> в Секреты</div>
          <div>3. Добавьте <code className="bg-secondary px-1 rounded">TELEGRAM_CHAT_ID</code> (ваш ID из @userinfobot)</div>
        </div>
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ signals, loading, onScan, market }: {
  signals: PumpSignal[];
  loading: boolean;
  onScan: () => void;
  market: MarketPair[];
}) {
  const pumps = signals.filter(s => s.type === "Pump");
  const dumps = signals.filter(s => s.type === "Dump");
  const btc = market.find(p => p.symbol === "BTC/USDT" || p.symbol === "BTCUSDT");
  const topSignal = signals[0];

  return (
    <div className="flex flex-col gap-3 fade-in">
      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Пампов сегодня</div>
          <div className="font-mono text-2xl font-bold bull">{pumps.length}</div>
          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><span className="text-base">🚀</span> Pump-сигналы</div>
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Дампов сегодня</div>
          <div className="font-mono text-2xl font-bold bear">{dumps.length}</div>
          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><span className="text-base">📉</span> Dump-сигналы</div>
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">BTC/USDT</div>
          {btc ? (
            <>
              <div className="font-mono text-base font-semibold" style={{ color: btc.change >= 0 ? "hsl(var(--bull))" : "hsl(var(--bear))" }}>
                ${btc.price.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className={`text-xs font-mono mt-1 ${btc.change >= 0 ? "bull" : "bear"}`}>
                {btc.change >= 0 ? "+" : ""}{btc.change.toFixed(2)}%
              </div>
            </>
          ) : (
            <div className="font-mono text-base text-muted-foreground">...</div>
          )}
        </div>
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Сканирование</div>
          <div className="font-mono text-base font-semibold">80+ пар</div>
          <div className="text-xs text-muted-foreground mt-1">каждые 5 минут</div>
        </div>
      </div>

      {/* Top signal */}
      {topSignal && (
        <div>
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Последний сигнал</div>
          <PumpCard sig={topSignal} idx={0} />
        </div>
      )}

      {/* Market ticker */}
      {market.length > 0 && (
        <div className="panel rounded p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Рынок</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {market.slice(0, 8).map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs font-mono">
                <span className="text-muted-foreground">{p.symbol.replace("USDT", "")}</span>
                <span className={p.change >= 0 ? "bull" : "bear"}>{p.change >= 0 ? "+" : ""}{p.change.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Status */}
      <div className="panel rounded p-2.5 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full blink bg-bull" />
          <span className="text-xs font-mono">Binance API</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full blink bg-bull" />
          <span className="text-xs font-mono">Pump Detector</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full blink bg-bull" />
          <span className="text-xs font-mono">Cron 5m</span>
        </div>
        <button onClick={onScan} disabled={loading}
          className="ml-auto text-xs font-mono px-3 py-1 rounded border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-40 flex items-center gap-1.5">
          <Icon name="RefreshCw" size={10} className={loading ? "animate-spin" : ""} />
          {loading ? "Сканирую..." : "Скан сейчас"}
        </button>
      </div>
    </div>
  );
}

// ─── Ticker Tape ──────────────────────────────────────────────────────────────

function TickerTape({ pairs }: { pairs: MarketPair[] }) {
  if (!pairs.length) return null;
  const items = [...pairs, ...pairs];
  return (
    <div className="overflow-hidden border-b border-border shrink-0" style={{ background: "hsl(220 13% 7%)" }}>
      <div className="ticker-scroll inline-flex gap-6 py-1.5 px-4">
        {items.map((p, i) => (
          <div key={i} className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="font-mono text-xs text-muted-foreground">{p.symbol.replace("USDT", "")}</span>
            <span className="font-mono text-xs">{p.price >= 1000 ? p.price.toLocaleString("en-US", { maximumFractionDigits: 0 }) : fmtPrice(p.price)}</span>
            <span className={`font-mono text-xs ${p.change >= 0 ? "bull" : "bear"}`}>{p.change >= 0 ? "▲" : "▼"}{Math.abs(p.change).toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Nav ──────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "dashboard", label: "Дашборд", icon: "LayoutDashboard" },
  { id: "signals", label: "Сигналы", icon: "Zap" },
  { id: "history", label: "История", icon: "History" },
  { id: "stats", label: "Статистика", icon: "BarChart2" },
  { id: "telegram", label: "Telegram", icon: "Bell" },
];

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function Index() {
  const [active, setActive] = useState("dashboard");
  const [signals, setSignals] = useState<PumpSignal[]>([]);
  const [market, setMarket] = useState<MarketPair[]>([]);
  const [loading, setLoading] = useState(false);
  const isMobile = useIsMobile();
  const scanRef = useRef(false);

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
      const r = await fetch(`${API_SIGNALS}?action=scan`);
      const d = await r.json();
      if (d.signals !== undefined) setSignals(d.signals || []);
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
    scan();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setInterval(() => { fetchMarket(); scan(); }, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchMarket, scan]);

  const renderSection = () => {
    switch (active) {
      case "dashboard": return <Dashboard signals={signals} loading={loading} onScan={scan} market={market} />;
      case "signals": return <LiveFeed signals={signals} loading={loading} onScan={scan} />;
      case "history": return <History />;
      case "stats": return <StatsSection />;
      case "telegram": return <TelegramSection />;
      default: return <Dashboard signals={signals} loading={loading} onScan={scan} market={market} />;
    }
  };

  return (
    <div className={`flex flex-col ${isMobile ? "min-h-screen" : "h-screen overflow-hidden"}`}>
      {/* Header */}
      <header className="flex items-center justify-between px-3 md:px-4 py-2 border-b border-border shrink-0"
        style={{ background: "hsl(220 13% 7%)" }}>
        <div className="flex items-center gap-2 md:gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-lg">🚀</span>
            <span className="font-mono font-bold text-sm tracking-tight">PumpBot</span>
          </div>
          {!isMobile && (
            <>
              <div className="w-px h-4 bg-border" />
              <span className="text-xs text-muted-foreground font-mono">80+ пар · Binance · 15m</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 text-xs font-mono px-2 py-1 rounded border ${loading ? "border-gold/30 text-gold" : "border-bull/30 text-bull"}`}
            style={{ background: loading ? "hsl(43 96% 56% / 0.05)" : "hsl(158 64% 48% / 0.05)" }}>
            <div className={`w-1.5 h-1.5 rounded-full blink ${loading ? "bg-gold" : "bg-bull"}`} />
            {!isMobile && <span>{loading ? "сканирую..." : "активен 24/7"}</span>}
          </div>
          <button onClick={() => { fetchMarket(); scan(); }} disabled={loading}
            className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors disabled:opacity-40">
            <Icon name="RefreshCw" size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      {/* Ticker */}
      <TickerTape pairs={market} />

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
                  {item.id === "signals" && signals.length > 0 && (
                    <span className="ml-auto text-xs font-mono bg-primary text-primary-foreground rounded-full w-4 h-4 flex items-center justify-center leading-none">
                      {Math.min(signals.length, 9)}
                    </span>
                  )}
                </button>
              ))}
            </nav>
            <div className="border-t border-border p-3">
              <div className="text-xs text-muted-foreground font-mono space-y-1">
                <div className="flex justify-between"><span>Сигналов:</span><span className="text-foreground">{loading ? "..." : signals.length}</span></div>
                <div className="flex justify-between"><span>Pump:</span><span className="bull">{signals.filter(s => s.type === "Pump").length}</span></div>
                <div className="flex justify-between"><span>Dump:</span><span className="bear">{signals.filter(s => s.type === "Dump").length}</span></div>
              </div>
            </div>
          </aside>
        )}

        {/* Main Content */}
        <main className={`flex-1 overflow-y-auto p-3 md:p-4 ${isMobile ? "pb-20" : ""}`}>
          {renderSection()}
        </main>
      </div>

      {/* Mobile Bottom Nav */}
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