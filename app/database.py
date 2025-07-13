import os
from typing import AsyncGenerator

from asyncpg import Connection
from fastapi import HTTPException, Request

from schemas import DBUser, User
DATABASE_URL = str(os.getenv("DATABASE_URL"))

# ジェネレータ関数で共通化 依存性注入でconn取得部分を共通化
async def get_db_conn(request: Request) -> AsyncGenerator[Connection, None]:
    db_pool = request.app.state.db_pool
    async with db_pool.acquire() as conn:
        yield conn  # 非同期ジェネレータとして返す

async def get_user_from_db(username:str,conn:Connection):
    row = await conn.fetchrow("SELECT * FROM users WHERE login_id = $1",username)
    if row is None:
        raise HTTPException(status_code=404,detail="User is not found")
    dict_row = dict(row)
    user:DBUser = DBUser(user_id=dict_row["user_id"],login_id=dict_row["login_id"],user_name=dict_row["name"],created_at=dict_row["created_at"],hashed_password=dict_row["password"])
    return user