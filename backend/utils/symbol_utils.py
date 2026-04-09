"""
Symbol helpers for control plane / risk (no execution dependency).
"""

# Longest-first so e.g. FDUSD wins over USD substring edge cases.
_QUOTE_SUFFIXES = ("FDUSD", "USDC", "USDT", "BUSD")


def extract_quote_asset(symbol: str | None) -> str:
    """
    Infer futures quote asset from symbol (e.g. BTCUSDT → USDT, BTCUSDC → USDC).
    Falls back to USDT when unknown.
    """
    if not symbol:
        return "USDT"
    s = str(symbol).strip().upper()
    if not s:
        return "USDT"
    for q in _QUOTE_SUFFIXES:
        if s.endswith(q):
            return q
    return "USDT"
