def win_loss_streak(trades):
    streaks = []
    cur = 0
    last = None

    for t in trades:
        win = t["result"] > 0

        if last is None or win == last:
            cur += 1
        else:
            streaks.append(cur)
            cur = 1

        last = win

    streaks.append(cur)
    return streaks
