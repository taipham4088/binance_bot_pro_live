# ==================================================
# SHORT ENGINE – MIRROR KIẾN TRÚC LONG ENGINE
# RANGE → TREND | BREAKOUT → RETEST → ENTRY
# ==================================================

import pandas as pd

# ===== PARAMS (GIỮ NGUYÊN TỪ SHORT GỐC) =====

MOMENTUM_LOOKBACK = 5
RANGE_LEVELS = [20,30,40,50,60,70,80]
BREAK_EXPANSION = 1.2
RANGE_MAX_BARS = 30
RANGE_MAX_DEPTH = 70



VN_OFFSET = pd.Timedelta(hours=7)
BLOCK_HOURS_VN = {1,7,12,13,14}


# ==================================================
# INIT STATE  (MIRROR LONG)
# ==================================================

def init_short_state():
    return {
        "waiting_retest": False,
        "just_breakout": False,

        "breakout_time": None,
        "breakout_level": None,
        "breakout_swing_high": None,
        "breakout_type": None,

        "breakout_h1_range_low": None,
        "breakout_h1_ema200": None,
        "breakout_h1_range_low_dist_ema200_pct": None,

        "retest_time": None,
        "retest_high": None,

        "bars_since_breakout": 0,
        "max_retest_high": None
    }


# ==================================================
# PROCESS SHORT
# ==================================================

def process_short(i, row, df, state, equity, context):

    waiting_retest = state["waiting_retest"]
    just_breakout = state["just_breakout"]

    breakout_time = state["breakout_time"]
    breakout_level = state["breakout_level"]
    breakout_swing_high = state["breakout_swing_high"]
    breakout_type = state["breakout_type"]

    breakout_h1_range_low = state["breakout_h1_range_low"]
    breakout_h1_ema200 = state["breakout_h1_ema200"]
    breakout_h1_range_low_dist_ema200_pct = state["breakout_h1_range_low_dist_ema200_pct"]

    retest_time = state["retest_time"]
    retest_high = state["retest_high"]

    bars_since_breakout = state["bars_since_breakout"]
    max_retest_high = state["max_retest_high"]

    # =============================
    # RANGE BREAKOUT ONLY (SHORT)
    # =============================

    candle_range = row['high'] - row['low']
    avg_range = (df['high'].iloc[i-MOMENTUM_LOOKBACK:i] - df['low'].iloc[i-MOMENTUM_LOOKBACK:i]).mean()

    if not waiting_retest:
        for lookback in RANGE_LEVELS:
            base = df.iloc[i-lookback:i]
            base_high = base['high'].max()
            base_low  = base['low'].min()

            if row['close'] < base_low and candle_range >= avg_range * BREAK_EXPANSION:

                tmp_dist = (row['ema200'] - row['range_low']) / row['ema200'] * 100
                if not (1 < tmp_dist < 10):
                    continue

                breakout_type = "range"
                breakout_time = row['time']
                breakout_level = base_low
                breakout_swing_high = base_high

                breakout_h1_range_low = row['range_low']
                breakout_h1_ema200 = row['ema200']
                breakout_h1_range_low_dist_ema200_pct = tmp_dist

                waiting_retest = True
                just_breakout = True

                bars_since_breakout = 0
                max_retest_high = None
                break

    # =============================
    # RETEST → TOUCH ENTRY (SHORT)
    # =============================

    if waiting_retest and breakout_level:

        if just_breakout:
            just_breakout = False
            state.update(locals())
            return None

        bars_since_breakout += 1

        if max_retest_high is None:
            max_retest_high = row['high']
        else:
            max_retest_high = max(max_retest_high, row['high'])

        denom = max(1e-9, breakout_swing_high - breakout_level)
        retest_depth_pct = (max_retest_high - breakout_level) / denom * 100

        if bars_since_breakout > RANGE_MAX_BARS or retest_depth_pct > RANGE_MAX_DEPTH:
            waiting_retest = False
            state.update(locals())
            return None

        if row['close'] > breakout_level:
            waiting_retest = False
            state.update(locals())
            return None

        if row['high'] >= breakout_level:

            entry_hour_vn = (row['time'] + VN_OFFSET).hour
            if entry_hour_vn in BLOCK_HOURS_VN:
                state.update(locals())
                return None

            retest_time = row['time']
            retest_high = row['high']

            entry = breakout_level
            sl = breakout_swing_high
            risk_money = equity * context.risk_per_trade
            tp = entry - context.rr * (sl - entry)

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
                'entry_dist_ema200_pct': (row['ema200'] - entry) / row['ema200'] * 100,

                'h1_range_high_at_breakout': breakout_h1_range_low,
                'ema200_1h_at_breakout': breakout_h1_ema200,
                'h1_range_high_dist_ema200_pct': breakout_h1_range_low_dist_ema200_pct,

                'breakout_time':breakout_time,
                'breakout_time_vn':breakout_time+VN_OFFSET,
                'breakout_level':breakout_level,
                'breakout_swing_low':breakout_swing_high,

                'retest_time':retest_time,
                'retest_time_vn':retest_time+VN_OFFSET,
                'retest_low':retest_high,
                'retest_depth_pct':retest_depth_pct,
                'bars_since_breakout': bars_since_breakout
            }

            waiting_retest = False
            breakout_time = breakout_level = breakout_swing_high = breakout_type = None
            breakout_h1_range_low = breakout_h1_ema200 = breakout_h1_range_low_dist_ema200_pct = None
            retest_time = retest_high = None

            state.update(locals())
            return position

    state.update(locals())
    return None
