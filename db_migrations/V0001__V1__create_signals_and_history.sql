
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.signals (
    id SERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    target_price DECIMAL(20, 8) NOT NULL,
    stop_price DECIMAL(20, 8) NOT NULL,
    confidence INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    rsi DECIMAL(10, 4),
    macd_signal DECIMAL(20, 8),
    bb_position DECIMAL(10, 4),
    volume_ratio DECIMAL(10, 4),
    fear_greed INTEGER,
    sentiment VARCHAR(20),
    analysis_text TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.trade_history (
    id SERIAL PRIMARY KEY,
    pair VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 4),
    pnl_usd DECIMAL(20, 2),
    status VARCHAR(20) DEFAULT 'open',
    duration_minutes INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signals_pair ON t_p73206386_global_trading_signa.signals(pair);
CREATE INDEX IF NOT EXISTS idx_signals_status ON t_p73206386_global_trading_signa.signals(status);
CREATE INDEX IF NOT EXISTS idx_trade_history_pair ON t_p73206386_global_trading_signa.trade_history(pair);
