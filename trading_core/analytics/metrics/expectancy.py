def expectancy(trades):
    if not trades:
        return 0

    wins = [t["result"] for t in trades if t["result"] > 0]
    losses = [t["result"] for t in trades if t["result"] <= 0]

    if not wins or not losses:
        return 0

    winrate = len(wins) / len(trades)
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))

    return winrate * avg_win - (1 - winrate) * avg_loss
