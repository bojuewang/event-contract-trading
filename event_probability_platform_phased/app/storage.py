from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, DateTime, MetaData, Numeric, Table, Text, BigInteger, Column, insert, func
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

metadata = MetaData()

event_ticks = Table(
    "event_ticks",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("market", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("source_ts", DateTime(timezone=True)),
    Column("ingested_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("price", Numeric),
    Column("raw_prob", Numeric),
    Column("fair_prob", Numeric),
    Column("meta", JSON),
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


async def write_ticks(engine: AsyncEngine, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    async with engine.begin() as conn:
        await conn.execute(insert(event_ticks), rows)
    return len(rows)
