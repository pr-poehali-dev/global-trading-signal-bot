
-- Обновляем старые сигналы — помечаем как архивные
UPDATE t_p73206386_global_trading_signa.signals SET status = 'archived' WHERE status != 'archived';
UPDATE t_p73206386_global_trading_signa.bot_trades SET status = 'archived' WHERE status NOT IN ('archived');

-- Виртуальный портфель
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.portfolio (
    id SERIAL PRIMARY KEY,
    initial_balance DECIMAL(12,2) NOT NULL DEFAULT 1000.00,
    current_balance DECIMAL(12,2) NOT NULL DEFAULT 1000.00,
    total_pnl DECIMAL(12,2) DEFAULT 0,
    total_pnl_pct DECIMAL(10,4) DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    peak_balance DECIMAL(12,2) DEFAULT 1000.00,
    max_drawdown_pct DECIMAL(10,4) DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO t_p73206386_global_trading_signa.portfolio
    (initial_balance, current_balance, peak_balance)
VALUES (1000.00, 1000.00, 1000.00);

-- Ежедневный трекинг баланса (для графика роста)
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.portfolio_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    balance DECIMAL(12,2) NOT NULL,
    pnl_day DECIMAL(12,2) DEFAULT 0,
    pnl_day_pct DECIMAL(10,4) DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO t_p73206386_global_trading_signa.portfolio_daily
    (date, balance, pnl_day, pnl_day_pct) VALUES (CURRENT_DATE, 1000.00, 0, 0);

-- Добавляю поля для плеча и виртуального P&L в сигналы
ALTER TABLE t_p73206386_global_trading_signa.signals
    ADD COLUMN IF NOT EXISTS leverage INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS position_size DECIMAL(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pnl_usdt DECIMAL(12,2) DEFAULT 0;
