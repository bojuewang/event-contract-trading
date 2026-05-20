from __future__ import annotations

"""
Kalshi WebSocket skeleton.

Kalshi WebSocket connections require authentication. Implement request signing with your
Kalshi credentials before production use. This file shows the subscription shape only.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import websockets


@dataclass
class KalshiWebSocketClient:
    ws_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    api_key_id: str = ""
    private_key_path: str = ""

    async def stream_orderbook(self, market_tickers: list[str]) -> AsyncIterator[dict]:
        # TODO: add required authenticated headers/signature.
        headers = {}
        async with websockets.connect(self.ws_url, additional_headers=headers) as ws:
            msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": market_tickers,
                },
            }
            await ws.send(json.dumps(msg))
            while True:
                raw = await ws.recv()
                yield json.loads(raw)


async def demo() -> None:
    client = KalshiWebSocketClient()
    async for message in client.stream_orderbook(["EXAMPLE-TICKER"]):
        print(message)
        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(demo())
