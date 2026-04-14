
-- Расширяем таблицу сигналов
ALTER TABLE t_p73206386_global_trading_signa.signals
  ADD COLUMN IF NOT EXISTS timeframe VARCHAR(10) DEFAULT '1h',
  ADD COLUMN IF NOT EXISTS actual_exit_price DECIMAL(20,8),
  ADD COLUMN IF NOT EXISTS result VARCHAR(10),
  ADD COLUMN IF NOT EXISTS result_pct DECIMAL(10,4),
  ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS score_bull INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS score_bear INTEGER DEFAULT 0;

-- Таблица подключённых бирж
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.exchange_connections (
    id SERIAL PRIMARY KEY,
    exchange_name VARCHAR(30) NOT NULL,
    api_key_hint VARCHAR(20),
    is_active BOOLEAN DEFAULT false,
    trade_mode VARCHAR(10) DEFAULT 'medium',
    max_position_usdt DECIMAL(10,2) DEFAULT 50,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица авто-сделок бота
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.bot_trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER REFERENCES t_p73206386_global_trading_signa.signals(id),
    exchange_name VARCHAR(30) NOT NULL,
    trade_mode VARCHAR(10) NOT NULL,
    pair VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    position_usdt DECIMAL(10,2) NOT NULL,
    leverage INTEGER DEFAULT 1,
    target_price DECIMAL(20,8),
    stop_price DECIMAL(20,8),
    exit_price DECIMAL(20,8),
    pnl_usdt DECIMAL(10,2),
    pnl_pct DECIMAL(10,4),
    status VARCHAR(20) DEFAULT 'open',
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

-- Таблица честной статистики (агрегат)
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.stats_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    signals_generated INTEGER DEFAULT 0,
    signals_win INTEGER DEFAULT 0,
    signals_loss INTEGER DEFAULT 0,
    signals_pending INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2),
    avg_profit_pct DECIMAL(10,4),
    avg_loss_pct DECIMAL(10,4),
    total_pnl_pct DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_trades_status ON t_p73206386_global_trading_signa.bot_trades(status);
CREATE INDEX IF NOT EXISTS idx_signals_result ON t_p73206386_global_trading_signa.signals(result);
CREATE INDEX IF NOT EXISTS idx_signals_created ON t_p73206386_global_trading_signa.signals(created_at);
