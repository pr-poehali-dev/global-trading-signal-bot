-- MEXC Auto-Bot: статус, сделки, баланс
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.mexc_bot_state (
  id              serial PRIMARY KEY,
  is_running      boolean NOT NULL DEFAULT false,
  leverage        integer NOT NULL DEFAULT 10,
  position_pct    numeric(5,4) NOT NULL DEFAULT 0.15,
  balance_usdt    numeric(12,2) NULL,
  started_at      timestamp NULL,
  stopped_at      timestamp NULL,
  updated_at      timestamp NOT NULL DEFAULT now()
);

INSERT INTO t_p73206386_global_trading_signa.mexc_bot_state
  (is_running, leverage, position_pct)
VALUES (false, 10, 0.15)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.mexc_bot_trades (
  id              serial PRIMARY KEY,
  signal_id       integer NULL REFERENCES t_p73206386_global_trading_signa.signals(id),
  pair            varchar(30) NOT NULL,
  symbol          varchar(30) NOT NULL,
  direction       varchar(10) NOT NULL,
  entry_price     numeric(20,8) NOT NULL,
  qty             numeric(20,8) NOT NULL,
  position_usdt   numeric(12,2) NOT NULL,
  leverage        integer NOT NULL DEFAULT 10,
  tp1_price       numeric(20,8) NULL,
  tp2_price       numeric(20,8) NULL,
  sl_price        numeric(20,8) NULL,
  tp1_pct         numeric(8,4) NULL,
  tp2_pct         numeric(8,4) NULL,
  sl_pct          numeric(8,4) NULL,
  score           integer NULL,
  factors_json    text NULL,
  mexc_order_id   varchar(64) NULL,
  status          varchar(20) NOT NULL DEFAULT 'open',
  exit_price      numeric(20,8) NULL,
  pnl_usdt        numeric(12,2) NULL,
  pnl_pct         numeric(10,4) NULL,
  close_reason    varchar(100) NULL,
  opened_at       timestamp NOT NULL DEFAULT now(),
  closed_at       timestamp NULL
);

CREATE INDEX IF NOT EXISTS idx_mexc_bot_trades_status ON t_p73206386_global_trading_signa.mexc_bot_trades(status);
CREATE INDEX IF NOT EXISTS idx_mexc_bot_trades_symbol ON t_p73206386_global_trading_signa.mexc_bot_trades(symbol, status);
