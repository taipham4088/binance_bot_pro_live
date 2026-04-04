export type TradingMode = "live" | "paper" | "backtest"

export type SessionConfig = {
  engine: string
  engine_profile: "range_trend" | "momentum"
  position_mode: "long_only" | "short_only" | "dual"
  symbol: string
  mode: TradingMode
}

export type Session = {
  id: string
  mode: TradingMode
  status: "running" | "stopped" | "idle"
  config: SessionConfig
}
