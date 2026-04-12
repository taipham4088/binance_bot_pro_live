# ==========================================================
# ===============  DUAL RANGE → TREND BACKTEST  ===========
# ==========================================================
# LONG ONLY – MIRROR FLOW BACKTEST LONG GỐC
# ==========================================================

import pandas as pd
import numpy as np

from engines.long_engine import process_long, init_long_state


# ==========================================================
# CONFIG
# ==========================================================

CSV_PATH = "futures_BTCUSDT_5m_FULL.csv"

INITIAL_BALANCE = 10000
RISK_PER_TRADE = 0.01
RR = 2.5

DAILY_STOP_LOSSES = 2
DAILY_DD_LIMIT = 0.03
VN_OFFSET = pd.Timedelta(hours=7)

H1_RANGE_LOOKBACK = 30
H1_MAX_TRADE_BARS = 5


# ==========================================================
# LOAD DATA
# ==========================================================

df = pd.read_csv(CSV_PATH)
df.columns = [c.lower() for c in df.columns]
df["time"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("time").reset_index(drop=True)


# ==========================================================
# RESAMPLE 1H – COPY 1–1 TỪ BACKTEST LONG GỐC
# ==========================================================

df_1h = df.set_index('time').resample('1h').agg({
    'open':'first','high':'max','low':'min','close':'last','volume':'sum'
}).dropna().reset_index()

df_1h['ema200'] = df_1h['close'].ewm(span=200, adjust=False).mean()
df_1h['range_high'] = df_1h['high'].rolling(H1_RANGE_LOOKBACK).max()
df_1h['range_low']  = df_1h['low'].rolling(H1_RANGE_LOOKBACK).min()
df_1h['break_up'] = df_1h['close'] > df_1h['range_high'].shift(1)
df_1h['break_id'] = (df_1h['break_up'] & ~df_1h['break_up'].shift(1).fillna(False)).cumsum()
df_1h['bars_since_break'] = df_1h.groupby('break_id').cumcount()
df_1h['valid_regime'] = (
    (df_1h['break_id'] > 0) &
    (df_1h['bars_since_break'] <= H1_MAX_TRADE_BARS) &
    (df_1h['close'] > df_1h['range_low'])
)

df = pd.merge_asof(
    df.sort_values('time'),
    df_1h[['time','ema200','close','valid_regime','bars_since_break','range_high']]
        .rename(columns={'close':'close_1h'}),
    on='time',
    direction='backward'
)


# ==========================================================
# INIT CORE  (GIỐNG BACKTEST LONG)
# ==========================================================

equity = INITIAL_BALANCE
position = None
trades = []

daily_loss_count = 0
daily_start_balance = INITIAL_BALANCE
blocked_until = None
current_day = None

daily_stop_days = set()
dd_block_events = []
block_log = []

long_state = init_long_state()


# ==========================================================
# BACKTEST LOOP – MIRROR FLOW LONG GỐC
# ==========================================================

for i in range(80, len(df)):

    row = df.iloc[i]
    day = row['time'].date()

    # ===== RESET NGÀY =====
    if current_day != day:
        current_day = day
        daily_loss_count = 0
        daily_start_balance = equity

    daily_dd = (daily_start_balance - equity) / daily_start_balance

    # ===== DAILY BLOCK (TRƯỚC TẤT CẢ) =====
    if blocked_until and row['time'] < blocked_until:
        continue

    if daily_loss_count >= DAILY_STOP_LOSSES:
        daily_stop_days.add(current_day)
        continue

    if daily_dd >= DAILY_DD_LIMIT:
        blocked_until = row['time'] + pd.Timedelta(hours=24)
        dd_block_events.append((row['time'], equity, daily_dd))
        block_log.append((current_day, "DD > LIMIT"))
        continue

    # ===== MANAGE POSITION =====
    if position:

        if row['low'] <= position['sl']:
            equity -= position['risk']
            trades.append({**position,
                           'exit_time':row['time'],
                           'exit_time_vn':row['time']+VN_OFFSET,
                           'exit_price':position['sl'],
                           'result':-position['risk'],
                           'balance':equity})
            daily_loss_count += 1
            position = None

        elif row['high'] >= position['tp']:
            win = position['risk'] * RR
            equity += win
            trades.append({**position,
                           'exit_time':row['time'],
                           'exit_time_vn':row['time']+VN_OFFSET,
                           'exit_price':position['tp'],
                           'result':win,
                           'balance':equity})
            position = None

        continue

    # ===== REGIME + TREND FILTER (GIỐNG LONG GỐC) =====
    if not row['valid_regime']:
        continue

    if row['close_1h'] <= row['ema200']:
        continue

    # ===== ENGINE =====
    long_signal = process_long(i, row, df, long_state, equity)

    if long_signal:
        position = long_signal
        position['side'] = 'LONG'


# ==========================================================
# EXPORT
# ==========================================================

trades_df = pd.DataFrame(trades)
trades_df.to_csv("BACKTEST_DUAL_TRADES.csv", index=False)

print("\n===== DUAL RANGE → TREND BACKTEST (LONG ONLY) =====")
print("Initial balance:", INITIAL_BALANCE)
print("Final balance:", round(equity,2))
print("Total trades:", len(trades_df))

if len(trades_df) > 0:
    wins = trades_df[trades_df["result"] > 0]
    print("Winrate:", round(len(wins)/len(trades_df)*100,2), "%")
    print("PnL:", round(trades_df["result"].sum(),2))

print("Daily stop days:", len(daily_stop_days))
print("DD blocks:", len(dd_block_events))
print("Saved: BACKTEST_DUAL_TRADES.csv")
