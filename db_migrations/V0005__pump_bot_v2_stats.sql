-- PumpBot v2: расширяем таблицу signals для детальной статистики
ALTER TABLE t_p73206386_global_trading_signa.signals
  ADD COLUMN IF NOT EXISTS leverage_recommended integer NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS position_usdt numeric(12,2) NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reasoning text NULL,
  ADD COLUMN IF NOT EXISTS factors_json text NULL,
  ADD COLUMN IF NOT EXISTS rvol numeric(6,2) NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS rsi_value numeric(6,1) NULL DEFAULT 50,
  ADD COLUMN IF NOT EXISTS pct_15m numeric(8,4) NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pct_45m numeric(8,4) NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pct_90m numeric(8,4) NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp1_price numeric(20,8) NULL,
  ADD COLUMN IF NOT EXISTS tp2_price numeric(20,8) NULL,
  ADD COLUMN IF NOT EXISTS tp3_price numeric(20,8) NULL,
  ADD COLUMN IF NOT EXISTS tp1_pct numeric(8,4) NULL,
  ADD COLUMN IF NOT EXISTS tp2_pct numeric(8,4) NULL,
  ADD COLUMN IF NOT EXISTS tp3_pct numeric(8,4) NULL,
  ADD COLUMN IF NOT EXISTS sl_pct numeric(8,4) NULL,
  ADD COLUMN IF NOT EXISTS atr_value numeric(20,8) NULL,
  ADD COLUMN IF NOT EXISTS profit_usdt numeric(12,2) NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS hit_tp1 boolean NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS hit_tp2 boolean NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS hit_tp3 boolean NULL DEFAULT false;

-- Таблица виртуального портфеля для pump-бота
CREATE TABLE IF NOT EXISTS t_p73206386_global_trading_signa.pump_portfolio (
  id serial PRIMARY KEY,
  initial_balance numeric(12,2) NOT NULL DEFAULT 1000,
  current_balance numeric(12,2) NOT NULL DEFAULT 1000,
  peak_balance    numeric(12,2) NOT NULL DEFAULT 1000,
  total_pnl       numeric(12,2) NOT NULL DEFAULT 0,
  total_pnl_pct   numeric(8,4)  NOT NULL DEFAULT 0,
  total_signals   integer NOT NULL DEFAULT 0,
  wins            integer NOT NULL DEFAULT 0,
  losses          integer NOT NULL DEFAULT 0,
  started_at      timestamp NOT NULL DEFAULT now(),
  updated_at      timestamp NOT NULL DEFAULT now()
);

INSERT INTO t_p73206386_global_trading_signa.pump_portfolio
  (initial_balance, current_balance, peak_balance)
VALUES (1000, 1000, 1000)
ON CONFLICT DO NOTHING;
