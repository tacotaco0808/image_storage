import os
from typing import AsyncGenerator

from asyncpg import Connection
from fastapi import Request
DATABASE_URL = str(os.getenv("DATABASE_URL"))

# ジェネレータ関数で共通化 依存性注入でconn取得部分を共通化
async def get_db_conn(request: Request) -> AsyncGenerator[Connection, None]:
    db_pool = request.app.state.db_pool
    async with db_pool.acquire() as conn:
        yield conn  # 非同期ジェネレータとして返す