import httpx


async def fetch_external_data():
    """
    Service for third-party integrations (e.g., market quotes, financial feeds, LLMs, Yahoo Finance).
    """
    return {
        "market_status": "OPEN",
        "benchmark_sp500": 5120.45,
        "sentiment_score": 0.78
    }
