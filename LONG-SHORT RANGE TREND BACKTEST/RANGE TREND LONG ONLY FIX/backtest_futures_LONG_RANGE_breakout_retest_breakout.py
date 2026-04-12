# ===== BOT RANGE → TREND ONLY (RETEST TOUCH ENTRY – KEEP LOG STRUCTURE) =====
# FIX ENGINE: tách breakout và retest thành 2 pha thời gian
# ADD LOG: H1 range high vs EMA200 tại thời điểm breakout 5m
# ADD FILTER: 1% < h1_range_high_dist_ema200_pct < 10%
# ADD ENTRY TIME FILTER (VN): loại bỏ entry 02h, 03h, 22h, 23h
# Giữ nguyên toàn bộ cấu trúc vào lệnh và log

import pandas as pd
import numpy as np

# =========================
# CONFIG
# =========================
CSV_PATH = "futures_BTCUSDT_5m_FULL.csv"
INITIAL_BALANCE = 10000
RISK_PER_TRADE = 0.01
RR = 2.5
SWING_LOOKBACK = 3
DAILY_STOP_LOSSES = 2
DAILY_DD_LIMIT = 0.03
VN_OFFSET = pd.Timedelta(hours=7)

H1_RANGE_LOOKBACK = 30
H1_MAX_TRADE_BARS = 5

BREAK_EXPANSION = 1.2
MOMENTUM_LOOKBACK = 5

RANGE_MAX_BARS = 30
RANGE_MAX_DEPTH = 70

RANGE_LEVELS = [20,30,40,50,60,70,80]

# =========================
# LOAD DATA
# =========================
df = pd.read_csv(CSV_PATH)
df.columns = [c.lower() for c in df.columns]
df['time'] = pd.to_datetime(df['timestamp'])
df = df.sort_values('time').reset_index(drop=True)

# =========================
# RESAMPLE 1H + EMA200
# =========================
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
    df_1h[['time','ema200','close','valid_regime','bars_since_break','range_high']].rename(columns={'close':'close_1h'}),
    on='time',
    direction='backward'
)

# =========================
# BACKTEST ENGINE
# =========================
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

waiting_retest = False
just_breakout = False

breakout_time = None
breakout_level = None
breakout_swing_low = None
breakout_type = None

breakout_h1_range_high = None
breakout_h1_ema200 = None
breakout_h1_range_high_dist_ema200_pct = None

retest_time = None
retest_low = None

bars_since_breakout = 0
max_retest_low = None

win_streak = 0
lose_streak = 0
max_win_streak = 0
max_lose_streak = 0

BLOCK_HOURS_VN = {2,3,22,23}

for i in range(80, len(df)):

    row = df.iloc[i]
    day = row['time'].date()

    if current_day != day:
        current_day = day
        daily_loss_count = 0
        daily_start_balance = equity

    daily_dd = (daily_start_balance - equity) / daily_start_balance

    if blocked_until and row['time'] < blocked_until:
        continue

    if daily_loss_count >= DAILY_STOP_LOSSES:
        daily_stop_days.add(current_day)
        continue

    if daily_dd >= DAILY_DD_LIMIT:
        blocked_until = row['time'] + pd.Timedelta(hours=24)
        dd_block_events.append((row['time'], equity, daily_dd))
        block_log.append((current_day, "DD > 3%"))
        continue

    if position:
        if row['low'] <= position['sl']:
            equity -= position['risk']
            trades.append({**position,'exit_time':row['time'],'exit_time_vn':row['time']+VN_OFFSET,'exit_price':position['sl'],'result':-position['risk'],'balance':equity})
            daily_loss_count += 1
            lose_streak += 1
            win_streak = 0
            max_lose_streak = max(max_lose_streak, lose_streak)
            position = None

        elif row['high'] >= position['tp']:
            win = position['risk'] * RR
            equity += win
            trades.append({**position,'exit_time':row['time'],'exit_time_vn':row['time']+VN_OFFSET,'exit_price':position['tp'],'result':win,'balance':equity})
            win_streak += 1
            lose_streak = 0
            max_win_streak = max(max_win_streak, win_streak)
            position = None
        continue

    if not row['valid_regime']:
        continue

    if row['close_1h'] <= row['ema200']:
        continue

    candle_range = row['high'] - row['low']
    avg_range = (df['high'].iloc[i-MOMENTUM_LOOKBACK:i] - df['low'].iloc[i-MOMENTUM_LOOKBACK:i]).mean()

    # =============================
    # RANGE BREAKOUT ONLY
    # =============================
    if not waiting_retest:
        for lookback in RANGE_LEVELS:
            base = df.iloc[i-lookback:i]
            base_high = base['high'].max()
            base_low  = base['low'].min()

            if row['close'] > base_high and candle_range >= avg_range * BREAK_EXPANSION:

                tmp_dist = (row['range_high'] - row['ema200']) / row['ema200'] * 100
                if not (1 < tmp_dist < 10):
                    continue

                breakout_type = "range"
                breakout_time = row['time']
                breakout_level = base_high
                breakout_swing_low = base_low

                breakout_h1_range_high = row['range_high']
                breakout_h1_ema200 = row['ema200']
                breakout_h1_range_high_dist_ema200_pct = tmp_dist

                waiting_retest = True
                just_breakout = True

                bars_since_breakout = 0
                max_retest_low = None
                break

    # =============================
    # RETEST → TOUCH ENTRY
    # =============================
    if waiting_retest and breakout_level:

        if just_breakout:
            just_breakout = False
            continue

        bars_since_breakout += 1

        if max_retest_low is None:
            max_retest_low = row['low']
        else:
            max_retest_low = min(max_retest_low, row['low'])

        denom = max(1e-9, breakout_level - breakout_swing_low)
        retest_depth_pct = (breakout_level - max_retest_low) / denom * 100

        if bars_since_breakout > RANGE_MAX_BARS or retest_depth_pct > RANGE_MAX_DEPTH:
            waiting_retest = False
            continue

        if row['close'] < breakout_level:
            waiting_retest = False
            continue

        if row['low'] <= breakout_level:

            # ===== ENTRY TIME FILTER (VN) =====
            entry_hour_vn = (row['time'] + VN_OFFSET).hour
            if entry_hour_vn in BLOCK_HOURS_VN:
                continue
            # ==================================

            retest_time = row['time']
            retest_low = row['low']

            entry = breakout_level
            sl = breakout_swing_low
            risk_money = equity * RISK_PER_TRADE
            tp = entry + RR * (entry - sl)

            position = {
                'entry_time':row['time'],
                'entry_time_vn':row['time']+VN_OFFSET,
                'entry_price':entry,
                'sl':sl,
                'tp':tp,
                'risk':risk_money,
                'breakout_type': "range",

                'close_1h_at_entry':row['close_1h'],
                'ema200_1h_at_entry':row['ema200'],
                'entry_dist_ema200_pct': (entry - row['ema200']) / row['ema200'] * 100,

                'h1_range_high_at_breakout': breakout_h1_range_high,
                'ema200_1h_at_breakout': breakout_h1_ema200,
                'h1_range_high_dist_ema200_pct': breakout_h1_range_high_dist_ema200_pct,

                'breakout_time':breakout_time,
                'breakout_time_vn':breakout_time+VN_OFFSET,
                'breakout_level':breakout_level,
                'breakout_swing_low':breakout_swing_low,
                'retest_time':retest_time,
                'retest_time_vn':retest_time+VN_OFFSET,
                'retest_low':retest_low,
                'retest_depth_pct':retest_depth_pct,
                'bars_since_breakout': bars_since_breakout
            }

            waiting_retest = False
            breakout_time = breakout_level = breakout_swing_low = breakout_type = None
            breakout_h1_range_high = breakout_h1_ema200 = breakout_h1_range_high_dist_ema200_pct = None
            retest_time = retest_low = None

# =========================
# EXPORT + REPORT
# =========================
trades_df = pd.DataFrame(trades)
trades_df.to_csv("BACKTEST_LONG_TRADES.csv", index=False)
pd.DataFrame(block_log, columns=["date","reason"]).to_csv("RISK_BLOCK_LOG.csv", index=False)

if len(trades_df) == 0:
    print("\nKHÔNG CÓ LỆNH NÀO.")
else:
    trades_df['year'] = pd.to_datetime(trades_df['entry_time']).dt.year
    wins = trades_df[trades_df['result'] > 0]

    print("\n===== BACKTEST FUTURES LONG – RANGE → TREND ONLY (TOUCH ENTRY) =====")
    print("Số dư ban đầu:", INITIAL_BALANCE)
    print("Số dư cuối:", round(equity, 2))
    print("Tổng số lệnh:", len(trades_df))
    print("Winrate:", round(len(wins) / len(trades_df) * 100, 2), "%")
    print("Chuỗi thắng dài nhất:", max_win_streak)
    print("Chuỗi thua dài nhất:", max_lose_streak)

    print("\n===== QUẢN LÝ RỦI RO =====")
    print("Số ngày bị DAILY STOP:", len(daily_stop_days))
    print("Số lần DD > 3%:", len(dd_block_events))

    print("\n===== THỐNG KÊ THEO NĂM =====")
    for y in sorted(trades_df['year'].unique()):
        sub = trades_df[trades_df['year'] == y]
        w = sub[sub['result'] > 0]
        print(f"\nNĂM {y}")
        print(" Tổng lệnh:", len(sub))
        print(" Winrate:", round(len(w) / len(sub) * 100, 2), "%")
        print(" Lợi nhuận:", round(sub['result'].sum(), 2))

print("\nĐã lưu lịch sử lệnh: BACKTEST_LONG_TRADES.csv")
print("Đã lưu log block: RISK_BLOCK_LOG.csv")
