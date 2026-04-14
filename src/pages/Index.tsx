import { useState, useEffect, useRef } from "react";
import Icon from "@/components/ui/icon";

// ─── Mock Data ───────────────────────────────────────────────────────────────

const PAIRS = [
  { symbol: "BTC/USDT", price: 67842.50, change: 2.34, volume: "1.24B" },
  { symbol: "ETH/USDT", price: 3521.80, change: 1.87, volume: "584M" },
  { symbol: "SOL/USDT", price: 182.45, change: -0.92, volume: "312M" },
  { symbol: "BNB/USDT", price: 602.30, change: 0.45, volume: "198M" },
  { symbol: "XRP/USDT", price: 0.6234, change: -1.23, volume: "412M" },
  { symbol: "DOGE/USDT", price: 0.1876, change: 3.12, volume: "289M" },
];

const SIGNALS = [
  { id: 1, pair: "BTC/USDT", type: "LONG", exchange: "Binance", entry: 67200, target: 69800, stop: 65900, confidence: 87, status: "active", time: "14:23" },
  { id: 2, pair: "ETH/USDT", type: "LONG", exchange: "Bybit", entry: 3480, target: 3720, stop: 3380, confidence: 79, status: "active", time: "14:01" },
  { id: 3, pair: "SOL/USDT", type: "SHORT", exchange: "OKX", entry: 188, target: 172, stop: 194, confidence: 71, status: "active", time: "13:45" },
  { id: 4, pair: "BNB/USDT", type: "LONG", exchange: "Binance", entry: 595, target: 625, stop: 582, confidence: 83, status: "waiting", time: "13:12" },
  { id: 5, pair: "XRP/USDT", type: "SHORT", exchange: "OKX", entry: 0.638, target: 0.598, stop: 0.655, confidence: 68, status: "waiting", time: "12:58" },
];

const HISTORY = [
  { id: 1, pair: "BTC/USDT", type: "LONG", entry: 64200, exit: 67100, pnl: 4.51, pnlUSD: 891, exchange: "Binance", date: "14 апр", duration: "3ч 12м" },
  { id: 2, pair: "ETH/USDT", type: "SHORT", entry: 3650, exit: 3520, pnl: 3.56, pnlUSD: 712, exchange: "Bybit", date: "13 апр", duration: "5ч 40м" },
  { id: 3, pair: "SOL/USDT", type: "LONG", entry: 192, exit: 184, pnl: -4.17, pnlUSD: -334, exchange: "OKX", date: "13 апр", duration: "2ч 05м" },
  { id: 4, pair: "BNB/USDT", type: "LONG", entry: 578, exit: 608, pnl: 5.19, pnlUSD: 600, exchange: "Binance", date: "12 апр", duration: "8ч 22м" },
  { id: 5, pair: "DOGE/USDT", type: "SHORT", entry: 0.198, exit: 0.185, pnl: 6.57, pnlUSD: 394, exchange: "Bybit", date: "12 апр", duration: "1ч 18м" },
  { id: 6, pair: "XRP/USDT", type: "LONG", entry: 0.598, exit: 0.634, pnl: 6.02, pnlUSD: 482, exchange: "OKX", date: "11 апр", duration: "6ч 54м" },
  { id: 7, pair: "BTC/USDT", type: "SHORT", entry: 69200, exit: 70100, pnl: -1.30, pnlUSD: -261, exchange: "Binance", date: "11 апр", duration: "4ч 31м" },
];

const NOTIFICATIONS_DATA = [
  { id: 1, type: "signal", text: "Новый сигнал LONG на BTC/USDT — уверенность 87%", time: "2 мин назад", read: false },
  { id: 2, type: "tp", text: "Take Profit достигнут: ETH/USDT +3.56% (+$712)", time: "1ч назад", read: false },
  { id: 3, type: "signal", text: "Новый сигнал SHORT на SOL/USDT — уверенность 71%", time: "2ч назад", read: false },
  { id: 4, type: "system", text: "Подключение к Binance восстановлено", time: "3ч назад", read: true },
  { id: 5, type: "sl", text: "Stop Loss сработал: SOL/USDT -4.17% (-$334)", time: "Вчера", read: true },
  { id: 6, type: "tp", text: "Take Profit достигнут: BNB/USDT +5.19% (+$600)", time: "Вчера", read: true },
  { id: 7, type: "system", text: "Bybit API подключён успешно", time: "2 дня назад", read: true },
];

// ─── Candle Chart ─────────────────────────────────────────────────────────────

function generateCandles(count: number) {
  let price = 67000;
  return Array.from({ length: count }, (_, i) => {
    const dir = Math.random() > 0.45 ? 1 : -1;
    const body = Math.random() * 600 + 100;
    const open = price;
    const close = price + dir * body;
    const wick = Math.random() * 300;
    const high = Math.max(open, close) + wick;
    const low = Math.min(open, close) - Math.random() * 300;
    price = close;
    return { open, close, high, low, index: i };
  });
}

function CandleChart() {
  const candles = useRef(generateCandles(60));
  const W = 900, H = 200;
  const padding = { top: 12, bottom: 20, left: 4, right: 56 };
  const chartW = W - padding.left - padding.right;
  const chartH = H - padding.top - padding.bottom;

  const allPrices = candles.current.flatMap(c => [c.high, c.low]);
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const range = maxP - minP || 1;

  const toY = (p: number) => padding.top + chartH - ((p - minP) / range) * chartH;
  const candleW = chartW / candles.current.length;

  const priceLabels = Array.from({ length: 5 }, (_, i) => {
    const p = minP + (range / 4) * i;
    return { price: p, y: toY(p) };
  });

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
      {priceLabels.map((l, i) => (
        <g key={i}>
          <line x1={padding.left} y1={l.y} x2={W - padding.right} y2={l.y}
            stroke="hsl(220 13% 14%)" strokeWidth="1" strokeDasharray="3,6" />
          <text x={W - padding.right + 4} y={l.y + 3.5}
            fill="hsl(215 12% 40%)" fontSize="9" fontFamily="IBM Plex Mono">
            {(l.price / 1000).toFixed(1)}k
          </text>
        </g>
      ))}
      {candles.current.map((c, i) => {
        const x = padding.left + i * candleW + candleW * 0.15;
        const w = candleW * 0.7;
        const isUp = c.close >= c.open;
        const color = isUp ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)";
        const bodyTop = toY(Math.max(c.open, c.close));
        const bodyH = Math.max(Math.abs(toY(c.open) - toY(c.close)), 1);
        const cx = x + w / 2;
        return (
          <g key={i}>
            <line x1={cx} y1={toY(c.high)} x2={cx} y2={toY(c.low)} stroke={color} strokeWidth="1" opacity="0.8" />
            <rect x={x} y={bodyTop} width={w} height={bodyH} fill={color} opacity={isUp ? 0.9 : 0.85} />
          </g>
        );
      })}
      {candles.current.map((c, i) => {
        const x = padding.left + i * candleW + candleW * 0.15;
        const w = candleW * 0.7;
        const isUp = c.close >= c.open;
        const vol = Math.random() * 18 + 3;
        return (
          <rect key={i} x={x} y={H - padding.bottom - vol} width={w} height={vol}
            fill={isUp ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)"} opacity="0.25" />
        );
      })}
    </svg>
  );
}

function Sparkline({ positive }: { positive: boolean }) {
  const pts = useRef(Array.from({ length: 20 }, (_, i) => {
    const base = positive ? 10 + i * 1.2 : 36 - i * 1.2;
    return base + (Math.random() - 0.5) * 8;
  }));
  const min = Math.min(...pts.current), max = Math.max(...pts.current);
  const norm = pts.current.map(p => ((p - min) / (max - min || 1)) * 26 + 4);
  const path = norm.map((y, i) => `${(i / (norm.length - 1)) * 72},${34 - y}`).join(" ");
  const color = positive ? "hsl(158 64% 48%)" : "hsl(0 72% 51%)";
  return (
    <svg width="72" height="34" viewBox="0 0 72 34">
      <polyline points={path} fill="none" stroke={color} strokeWidth="1.5" opacity="0.75" />
    </svg>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard() {
  const [tick, setTick] = useState(0);
  const btcPrice = (67842.50 + Math.sin(tick * 0.4) * 95).toFixed(2);

  useEffect(() => {
    const t = setInterval(() => setTick(p => p + 1), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex flex-col h-full gap-3 overflow-y-auto pr-1 fade-in">
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Баланс портфеля", value: "$24,841.30", sub: "+$1,241 сегодня", pos: true, icon: "Wallet" },
          { label: "P&L за месяц", value: "+$3,492", sub: "+16.4% ROI", pos: true, icon: "TrendingUp" },
          { label: "Активных сигналов", value: "3", sub: "2 LONG · 1 SHORT", pos: null, icon: "Zap" },
          { label: "Win Rate", value: "72.3%", sub: "из 148 сделок", pos: true, icon: "Target" },
        ].map((m, i) => (
          <div key={i} className="panel rounded p-4 fade-in" style={{ animationDelay: `${i * 0.05}s` }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-muted-foreground text-xs uppercase tracking-wider">{m.label}</span>
              <Icon name={m.icon} size={13} className="text-muted-foreground" />
            </div>
            <div className="font-mono text-xl font-semibold"
              style={{ color: m.pos === true ? "hsl(var(--bull))" : m.pos === false ? "hsl(var(--bear))" : "hsl(var(--foreground))" }}>
              {m.value}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{m.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-3" style={{ flex: "1 1 0", minHeight: 0 }}>
        <div className="col-span-2 panel rounded flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <div className="flex items-center gap-3">
              <span className="font-mono font-semibold text-sm">BTC/USDT</span>
              <span className="font-mono text-base bull">{Number(btcPrice).toLocaleString()}</span>
              <span className="badge-bull text-xs px-2 py-0.5 rounded font-mono">+2.34%</span>
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
              <span>H: <span className="text-foreground">68,200</span></span>
              <span>L: <span className="text-foreground">66,100</span></span>
              <span>Vol: <span className="text-foreground">1.24B</span></span>
            </div>
            <div className="flex gap-1">
              {["1м", "5м", "15м", "1ч", "4ч", "1д"].map(t => (
                <button key={t} className={`text-xs px-2 py-0.5 rounded font-mono transition-colors ${t === "1ч" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{t}</button>
              ))}
            </div>
          </div>
          <div className="flex-1 p-2 min-h-0">
            <CandleChart />
          </div>
        </div>

        <div className="panel rounded flex flex-col">
          <div className="px-4 py-2 border-b border-border flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Рынок</span>
            <div className="flex gap-1">
              {["Все", "Spot"].map(f => (
                <button key={f} className={`text-xs px-2 py-0.5 rounded font-mono ${f === "Все" ? "text-primary" : "text-muted-foreground"}`}>{f}</button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {PAIRS.map((p, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2 row-hover border-b border-border/40">
                <div className="flex items-center gap-2">
                  <Sparkline positive={p.change > 0} />
                  <div>
                    <div className="font-mono text-xs font-medium">{p.symbol}</div>
                    <div className="text-muted-foreground text-xs font-mono">{p.volume}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-xs">{p.price < 1 ? p.price.toFixed(4) : p.price.toLocaleString()}</div>
                  <div className={`font-mono text-xs ${p.change > 0 ? "bull" : "bear"}`}>
                    {p.change > 0 ? "+" : ""}{p.change}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel rounded p-2.5 flex items-center gap-6">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">Биржи:</span>
        {[
          { name: "Binance", ping: "12ms" },
          { name: "Bybit", ping: "18ms" },
          { name: "OKX", ping: "24ms" },
        ].map((e, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-bull blink" />
            <span className="font-mono text-xs">{e.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{e.ping}</span>
          </div>
        ))}
        <div className="ml-auto font-mono text-xs text-muted-foreground">
          {new Date().toLocaleTimeString("ru-RU")}
        </div>
      </div>
    </div>
  );
}

// ─── Signals ──────────────────────────────────────────────────────────────────

function Signals() {
  return (
    <div className="flex flex-col h-full gap-3 fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Активные сигналы</span>
          <span className="badge-bull text-xs px-2 py-0.5 rounded-full font-mono">3 активных</span>
        </div>
        <div className="flex gap-2">
          {["Все", "LONG", "SHORT", "Ожидание"].map(f => (
            <button key={f} className={`text-xs px-3 py-1 rounded border font-mono transition-colors ${f === "Все" ? "border-primary text-primary" : "border-border text-muted-foreground hover:border-foreground hover:text-foreground"}`}>{f}</button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
        {SIGNALS.map((s, i) => (
          <div key={s.id} className="panel rounded p-4 fade-in row-hover" style={{ animationDelay: `${i * 0.04}s` }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded ${s.type === "LONG" ? "badge-bull" : "badge-bear"}`}>{s.type}</span>
                <div>
                  <div className="font-mono font-semibold text-sm">{s.pair}</div>
                  <div className="text-xs text-muted-foreground">{s.exchange} · {s.time}</div>
                </div>
              </div>
              <div className="flex items-center gap-8">
                {[
                  { label: "Вход", val: s.entry, color: "" },
                  { label: "Цель", val: s.target, color: "bull" },
                  { label: "Стоп", val: s.stop, color: "bear" },
                ].map((f, fi) => (
                  <div key={fi} className="text-center">
                    <div className="text-xs text-muted-foreground mb-0.5">{f.label}</div>
                    <div className={`font-mono text-sm ${f.color}`}>{f.val}</div>
                  </div>
                ))}
                <div className="text-center">
                  <div className="text-xs text-muted-foreground mb-0.5">Потенциал</div>
                  <div className={`font-mono text-sm ${s.type === "LONG" ? "bull" : "bear"}`}>
                    {s.type === "LONG"
                      ? `+${(((s.target - s.entry) / s.entry) * 100).toFixed(1)}%`
                      : `+${(((s.entry - s.target) / s.entry) * 100).toFixed(1)}%`}
                  </div>
                </div>
                <div className="text-center min-w-24">
                  <div className="text-xs text-muted-foreground mb-1">Уверенность</div>
                  <div className="w-24 h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{
                      width: `${s.confidence}%`,
                      background: s.confidence > 80 ? "hsl(var(--bull))" : s.confidence > 70 ? "hsl(var(--gold))" : "hsl(var(--bear))"
                    }} />
                  </div>
                  <div className="font-mono text-xs mt-0.5">{s.confidence}%</div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded font-mono ${s.status === "active" ? "badge-bull" : "badge-gold"}`}>
                  {s.status === "active" ? "● Активен" : "○ Ожидание"}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="panel rounded p-3 grid grid-cols-4 gap-4 text-center">
        {[
          { label: "Сигналов сегодня", value: "12" },
          { label: "Ср. уверенность", value: "77.6%" },
          { label: "LONG / SHORT", value: "8 / 4" },
          { label: "Ср. потенциал", value: "+4.2%" },
        ].map((s, i) => (
          <div key={i}>
            <div className="font-mono text-base font-semibold">{s.value}</div>
            <div className="text-xs text-muted-foreground">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── History ──────────────────────────────────────────────────────────────────

function History() {
  return (
    <div className="flex flex-col h-full gap-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">История сделок</span>
        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="bull">+$2,879 прибыль</span>
          <span className="text-muted-foreground">|</span>
          <span className="bear">-$595 убыток</span>
          <span className="text-muted-foreground">|</span>
          <span>Итого: <span className="bull font-semibold">+$2,284</span></span>
        </div>
      </div>

      <div className="panel rounded flex-1 overflow-hidden flex flex-col">
        <div className="grid font-mono text-xs text-muted-foreground uppercase tracking-wider px-4 py-2 border-b border-border bg-card"
          style={{ gridTemplateColumns: "1.2fr 70px 80px 1fr 1fr 1fr 80px 90px" }}>
          <span>Пара</span><span>Тип</span><span>Биржа</span>
          <span>Вход</span><span>Выход</span><span>P&L</span>
          <span>Длит.</span><span>Дата</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {HISTORY.map((h, i) => (
            <div key={h.id} className="grid items-center px-4 py-2.5 border-b border-border/40 row-hover fade-in"
              style={{ gridTemplateColumns: "1.2fr 70px 80px 1fr 1fr 1fr 80px 90px", animationDelay: `${i * 0.03}s` }}>
              <span className="font-mono text-xs font-medium">{h.pair}</span>
              <span className={`font-mono text-xs font-bold ${h.type === "LONG" ? "bull" : "bear"}`}>{h.type}</span>
              <span className="text-xs text-muted-foreground">{h.exchange}</span>
              <span className="font-mono text-xs">{h.entry.toLocaleString()}</span>
              <span className="font-mono text-xs">{h.exit.toLocaleString()}</span>
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs font-semibold ${h.pnl > 0 ? "bull" : "bear"}`}>
                  {h.pnl > 0 ? "+" : ""}{h.pnl}%
                </span>
                <span className={`font-mono text-xs ${h.pnlUSD > 0 ? "bull" : "bear"}`}>
                  {h.pnlUSD > 0 ? "+" : ""}${Math.abs(h.pnlUSD)}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">{h.duration}</span>
              <span className="text-xs text-muted-foreground">{h.date}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Всего сделок", value: "148", icon: "Hash", pos: null },
          { label: "Win Rate", value: "72.3%", icon: "Target", pos: true },
          { label: "Лучшая сделка", value: "+$891", icon: "Trophy", pos: true },
          { label: "Средний P&L", value: "+3.2%", icon: "TrendingUp", pos: true },
          { label: "Макс. просадка", value: "-4.17%", icon: "TrendingDown", pos: false },
        ].map((s, i) => (
          <div key={i} className="panel rounded p-3 text-center">
            <Icon name={s.icon} size={13} className={`mx-auto mb-1 ${s.pos === true ? "text-bull" : s.pos === false ? "text-bear" : "text-muted-foreground"}`} />
            <div className={`font-mono text-sm font-semibold ${s.pos === true ? "bull" : s.pos === false ? "bear" : ""}`}>{s.value}</div>
            <div className="text-xs text-muted-foreground">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Notifications ────────────────────────────────────────────────────────────

function NotificationsSection() {
  const [notifications, setNotifications] = useState(NOTIFICATIONS_DATA);
  const unread = notifications.filter(n => !n.read).length;

  const iconMap: Record<string, string> = { signal: "Zap", tp: "TrendingUp", sl: "TrendingDown", system: "Settings" };
  const colorMap: Record<string, string> = { signal: "gold", tp: "bull", sl: "bear", system: "text-muted-foreground" };

  return (
    <div className="flex flex-col h-full gap-3 fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Уведомления</span>
          {unread > 0 && <span className="badge-gold text-xs px-2 py-0.5 rounded-full font-mono">{unread} новых</span>}
        </div>
        <button onClick={() => setNotifications(n => n.map(x => ({ ...x, read: true })))}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors font-mono">
          Отметить все прочитанными
        </button>
      </div>
      <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
        {notifications.map((n, i) => (
          <div key={n.id}
            className={`panel rounded p-4 flex items-start gap-3 row-hover fade-in transition-all ${!n.read ? "border-l-2 border-l-primary" : ""}`}
            style={{ animationDelay: `${i * 0.04}s` }}
            onClick={() => setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, read: true } : x))}>
            <div className={`mt-0.5 ${colorMap[n.type]}`}>
              <Icon name={iconMap[n.type]} size={15} />
            </div>
            <div className="flex-1">
              <div className={`text-sm ${n.read ? "text-muted-foreground" : "text-foreground"}`}>{n.text}</div>
              <div className="text-xs text-muted-foreground mt-0.5 font-mono">{n.time}</div>
            </div>
            {!n.read && <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 blink" />}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Analytics ────────────────────────────────────────────────────────────────

function Analytics() {
  const weeklyData = [
    { day: "Пн", pnl: 420, trades: 5 },
    { day: "Вт", pnl: -180, trades: 3 },
    { day: "Ср", pnl: 890, trades: 8 },
    { day: "Чт", pnl: 340, trades: 4 },
    { day: "Пт", pnl: 712, trades: 6 },
    { day: "Сб", pnl: -120, trades: 2 },
    { day: "Вс", pnl: 242, trades: 3 },
  ];
  const max = Math.max(...weeklyData.map(d => Math.abs(d.pnl)));

  return (
    <div className="flex flex-col h-full gap-3 overflow-y-auto pr-1 fade-in">
      <span className="text-sm font-semibold">Аналитика</span>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2 panel rounded p-4">
          <div className="text-xs text-muted-foreground uppercase tracking-wider mb-4">P&L по дням (7д)</div>
          <div className="flex items-end gap-2 h-36">
            {weeklyData.map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span className={`font-mono text-xs ${d.pnl > 0 ? "bull" : "bear"}`}>{d.pnl > 0 ? "+" : ""}${d.pnl}</span>
                <div className="w-full flex items-end justify-center" style={{ height: "90px" }}>
                  <div className="w-full rounded-sm"
                    style={{ height: `${(Math.abs(d.pnl) / max) * 80}px`, background: d.pnl > 0 ? "hsl(var(--bull))" : "hsl(var(--bear))", opacity: 0.8 }} />
                </div>
                <span className="text-xs text-muted-foreground font-mono">{d.day}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <div className="panel rounded p-4">
            <div className="text-xs text-muted-foreground mb-1">Лучший день</div>
            <div className="font-mono text-lg bull font-semibold">+$890</div>
            <div className="text-xs text-muted-foreground">Среда · 8 сделок</div>
          </div>
          <div className="panel rounded p-4">
            <div className="text-xs text-muted-foreground mb-1">Итого за неделю</div>
            <div className="font-mono text-lg bull font-semibold">+$2,304</div>
            <div className="text-xs text-muted-foreground">31 сделка</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { name: "Binance", trades: 58, winrate: 74, pnl: "+$1,420", color: "hsl(43 96% 56%)" },
          { name: "Bybit", trades: 47, winrate: 70, pnl: "+$892", color: "hsl(210 80% 60%)" },
          { name: "OKX", trades: 43, winrate: 72, pnl: "+$972", color: "hsl(280 70% 60%)" },
        ].map((e, i) => (
          <div key={i} className="panel rounded p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-2 h-2 rounded-full" style={{ background: e.color }} />
              <span className="font-semibold text-sm">{e.name}</span>
            </div>
            <div className="space-y-2">
              {[
                { label: "Сделок", val: String(e.trades), cls: "" },
                { label: "Win Rate", val: `${e.winrate}%`, cls: "bull" },
                { label: "P&L", val: e.pnl, cls: "bull" },
              ].map((r, ri) => (
                <div key={ri} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{r.label}</span>
                  <span className={`font-mono ${r.cls}`}>{r.val}</span>
                </div>
              ))}
              <div className="w-full h-1 bg-secondary rounded-full overflow-hidden mt-1">
                <div className="h-full rounded-full" style={{ width: `${e.winrate}%`, background: e.color }} />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="panel rounded p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Топ пары по доходности</div>
        <div className="flex flex-col gap-2.5">
          {[
            { pair: "BTC/USDT", trades: 42, pnl: "+$1,240", winrate: 76 },
            { pair: "ETH/USDT", trades: 35, pnl: "+$820", winrate: 71 },
            { pair: "SOL/USDT", trades: 28, pnl: "+$480", winrate: 68 },
            { pair: "BNB/USDT", trades: 22, pnl: "+$320", winrate: 73 },
          ].map((p, i) => (
            <div key={i} className="flex items-center gap-4">
              <span className="font-mono text-xs text-muted-foreground w-4">{i + 1}</span>
              <span className="font-mono text-xs font-medium w-24">{p.pair}</span>
              <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${p.winrate}%` }} />
              </div>
              <span className="font-mono text-xs text-muted-foreground w-14 text-right">{p.trades} сд.</span>
              <span className="font-mono text-xs bull w-20 text-right">{p.pnl}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Settings ─────────────────────────────────────────────────────────────────

function Settings() {
  return (
    <div className="flex flex-col h-full gap-4 overflow-y-auto pr-1 fade-in">
      <span className="text-sm font-semibold">Настройки</span>

      <div className="panel rounded p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Подключение бирж</div>
        <div className="flex flex-col gap-4">
          {[
            { name: "Binance", key: "BN_••••••••XKQP", connected: true },
            { name: "Bybit", key: "BY_••••••••LMWZ", connected: true },
            { name: "OKX", key: "", connected: false },
          ].map((e, i) => (
            <div key={i} className="border border-border rounded p-3">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${e.connected ? "bg-bull blink" : "bg-muted-foreground"}`} />
                  <span className="font-semibold text-sm">{e.name}</span>
                </div>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${e.connected ? "badge-bull" : "badge-bear"}`}>
                  {e.connected ? "Подключено" : "Не подключено"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">API Key</label>
                  <input type="text" defaultValue={e.key} placeholder="Введите API Key..."
                    className="w-full bg-secondary border border-border rounded px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">Secret Key</label>
                  <input type="password" placeholder="Введите Secret Key..."
                    className="w-full bg-secondary border border-border rounded px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary" />
                </div>
              </div>
              <div className="flex gap-2 mt-2">
                <button className="text-xs px-3 py-1.5 bg-primary text-primary-foreground rounded font-mono hover:opacity-80 transition-opacity">
                  {e.connected ? "Обновить" : "Подключить"}
                </button>
                {e.connected && (
                  <button className="text-xs px-3 py-1.5 border border-border text-muted-foreground rounded font-mono hover:text-foreground transition-colors">
                    Отключить
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel rounded p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Параметры бота</div>
        <div className="grid grid-cols-2 gap-4">
          {[
            { label: "Мин. уверенность сигнала", value: "70", unit: "%" },
            { label: "Макс. размер позиции", value: "5", unit: "% от депозита" },
            { label: "Стоп-лосс по умолчанию", value: "2", unit: "%" },
            { label: "Тейк-профит по умолчанию", value: "4", unit: "%" },
            { label: "Макс. открытых сделок", value: "5", unit: "шт" },
            { label: "Таймфрейм анализа", value: "1ч", unit: "" },
          ].map((s, i) => (
            <div key={i}>
              <label className="text-xs text-muted-foreground block mb-1">{s.label}</label>
              <div className="flex items-center gap-2">
                <input type="text" defaultValue={s.value}
                  className="flex-1 bg-secondary border border-border rounded px-2 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:border-primary" />
                {s.unit && <span className="text-xs text-muted-foreground whitespace-nowrap">{s.unit}</span>}
              </div>
            </div>
          ))}
        </div>
        <button className="mt-4 text-xs px-4 py-2 bg-primary text-primary-foreground rounded font-mono hover:opacity-80 transition-opacity">
          Сохранить настройки
        </button>
      </div>

      <div className="panel rounded p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-4">Уведомления</div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Новые сигналы", on: true },
            { label: "Take Profit достигнут", on: true },
            { label: "Stop Loss сработал", on: true },
            { label: "Статус биржи", on: false },
            { label: "Telegram уведомления", on: true },
            { label: "Email дайджест", on: false },
          ].map((n, i) => (
            <div key={i} className="flex items-center justify-between py-1">
              <span className="text-xs">{n.label}</span>
              <div className={`w-8 h-4 rounded-full relative cursor-pointer transition-colors ${n.on ? "bg-primary" : "bg-secondary border border-border"}`}>
                <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${n.on ? "left-4" : "left-0.5"}`} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Ticker ───────────────────────────────────────────────────────────────────

function TickerTape() {
  const items = [...PAIRS, ...PAIRS];
  return (
    <div className="overflow-hidden border-b border-border" style={{ background: "hsl(220 13% 7%)" }}>
      <div className="ticker-scroll inline-flex gap-8 py-1.5 px-4">
        {items.map((p, i) => (
          <div key={i} className="flex items-center gap-2 whitespace-nowrap">
            <span className="font-mono text-xs text-muted-foreground">{p.symbol}</span>
            <span className="font-mono text-xs">{p.price < 1 ? p.price.toFixed(4) : p.price.toLocaleString()}</span>
            <span className={`font-mono text-xs ${p.change > 0 ? "bull" : "bear"}`}>
              {p.change > 0 ? "▲" : "▼"} {Math.abs(p.change)}%
            </span>
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
  { id: "notifications", label: "Уведомления", icon: "Bell" },
  { id: "analytics", label: "Аналитика", icon: "BarChart2" },
  { id: "settings", label: "Настройки", icon: "Settings" },
];

export default function Index() {
  const [active, setActive] = useState("dashboard");
  const unread = NOTIFICATIONS_DATA.filter(n => !n.read).length;

  const section = () => {
    switch (active) {
      case "dashboard": return <Dashboard />;
      case "signals": return <Signals />;
      case "history": return <History />;
      case "notifications": return <NotificationsSection />;
      case "analytics": return <Analytics />;
      case "settings": return <Settings />;
      default: return <Dashboard />;
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0" style={{ background: "hsl(220 13% 7%)" }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-5 rounded bg-primary flex items-center justify-center">
              <Icon name="Bot" size={12} className="text-primary-foreground" />
            </div>
            <span className="font-mono font-semibold text-sm tracking-tight">TradeBot</span>
          </div>
          <div className="w-px h-4 bg-border" />
          <span className="text-xs text-muted-foreground font-mono">Терминал v1.0</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs font-mono">
            <div className="w-1.5 h-1.5 rounded-full bg-bull blink" />
            <span className="text-muted-foreground">3 биржи онлайн</span>
          </div>
          <div className="w-px h-4 bg-border" />
          <span className="text-xs font-mono text-muted-foreground">Баланс: <span className="bull font-semibold">$24,841.30</span></span>
          <div className="w-px h-4 bg-border" />
          <button className="text-xs font-mono px-2.5 py-1 rounded border transition-colors"
            style={{ background: "hsl(158 64% 48% / 0.08)", borderColor: "hsl(158 64% 48% / 0.3)", color: "hsl(var(--bull))" }}>
            ● БОТ АКТИВЕН
          </button>
        </div>
      </header>

      {/* Ticker */}
      <TickerTape />

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-44 border-r border-border shrink-0 flex flex-col" style={{ background: "hsl(var(--sidebar-background))" }}>
          <nav className="flex-1 py-2">
            {NAV.map(item => (
              <button key={item.id} onClick={() => setActive(item.id)}
                className={`nav-item w-full flex items-center gap-3 px-4 py-2.5 text-left relative ${active === item.id ? "nav-active" : "text-sidebar-foreground"}`}>
                <Icon name={item.icon} size={14} />
                <span className="text-xs font-medium">{item.label}</span>
                {item.id === "notifications" && unread > 0 && (
                  <span className="ml-auto text-xs font-mono bg-primary text-primary-foreground rounded-full w-4 h-4 flex items-center justify-center leading-none">
                    {unread}
                  </span>
                )}
              </button>
            ))}
          </nav>
          <div className="border-t border-border p-3">
            <div className="text-xs text-muted-foreground font-mono space-y-1">
              <div className="flex justify-between"><span>Сигналов:</span><span className="text-foreground">12/день</span></div>
              <div className="flex justify-between"><span>Win rate:</span><span className="bull">72.3%</span></div>
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-hidden p-4">
          {section()}
        </main>
      </div>
    </div>
  );
}