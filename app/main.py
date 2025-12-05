import asyncio
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import timedelta, datetime
import asyncpg
from asyncpg.pool import Pool
from fastapi import FastAPI, WebSocket
import cloudinary, os
from dotenv import load_dotenv
from jose import jwt

load_dotenv()

DATABASE_URL = str(os.getenv("DATABASE_URL"))

# JWTブラックリスト管理用の辞書（トークン: 有効期限）
from datetime import datetime
import os
from jose import jwt
blacklisted_tokens = {}

def add_token_to_blacklist(token: str):
    """トークンをブラックリストに追加（有効期限付き）"""
    try:
        SECRET_KEY = os.getenv("SECRET_KEY")
        ALGORITHM = os.getenv("ALGORITHM")
        if SECRET_KEY and ALGORITHM:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                exp_datetime = datetime.fromtimestamp(exp_timestamp)
                blacklisted_tokens[token] = exp_datetime
    except Exception:
        # デコードに失敗した場合は、現在時刻から1時間後を設定
        blacklisted_tokens[token] = datetime.now() + timedelta(hours=1)

def cleanup_expired_tokens():
    """期限切れのトークンをブラックリストから削除"""
    now = datetime.now()
    expired_tokens = [token for token, exp_time in blacklisted_tokens.items() if now > exp_time]
    for token in expired_tokens:
        blacklisted_tokens.pop(token, None)
    if expired_tokens:
        print(f"期限切れトークン {len(expired_tokens)} 個を削除しました")

def is_token_blacklisted(token: str) -> bool:
    """トークンがブラックリストに含まれているかチェック"""
    if token in blacklisted_tokens:
        # 期限をチェック
        exp_time = blacklisted_tokens[token]
        if datetime.now() > exp_time:
            # 期限切れなので削除
            blacklisted_tokens.pop(token, None)
            return False
        return True
    return False

async def periodic_token_cleanup():
    """定期的にブラックリストの期限切れトークンをクリーンアップ"""
    while True:
        await asyncio.sleep(3600)  # 1時間ごとに実行
        cleanup_expired_tokens()

# 初期化（最初に一度だけ呼ぶ）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 前処理
    db_pool: Pool = await asyncpg.create_pool(DATABASE_URL) 
    app.state.db_pool = db_pool # fastapiのstateへ保持|poolはSQLへの接続を管理するオブジェクト

    print("✅ Connected to database")
    
    # ブラックリストクリーンアップタスクを開始
    cleanup_task = asyncio.create_task(periodic_token_cleanup())
    print("✅ Started token cleanup task")
    # テーブル作成を起動時に実行（1回だけ）
    async with app.state.db_pool.acquire() as conn: # acquireで１つ接続を借りて使い、async withが終わると自動で返却
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            public_id UUID PRIMARY KEY,
            user_id UUID,
            format TEXT NOT NULL,
            version INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id UUID NOT NULL,
            name VARCHAR NOT NULL,
            login_id VARCHAR NOT NULL UNIQUE,
            password VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id)
        );
        """)
    yield
    # 後処理
    cleanup_task.cancel()
    await app.state.db_pool.close()
    print("🛑 Disconnected from database")


app = FastAPI(lifespan=lifespan,root_path="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(os.getenv("FRONT_IP")),"http://localhost:5173"],
    allow_credentials=True,# JWT認証のためのクッキーを受け取る
    allow_methods=["*"],  # 全メソッド（GET, POSTなど）許可
    allow_headers=["*"],  # 全ヘッダー許可)
)
cloudinary.config(
    cloud_name = str(os.getenv("CLOUDINARY_CLOUD_NAME")),
    api_key = str(os.getenv("CLOUDINARY_API_KEY")),
    api_secret = str(os.getenv("CLOUDINARY_API_SECRET"))
)

# ルーターを登録
from routers import images, users, auth as auth_router
app.include_router(images.router)
app.include_router(users.router)
app.include_router(auth_router.router)

# WebSocket関連の処理は websocket_routes.py に移動
from websocket_routes import websocket_endpoint

@app.websocket("/ws/{ws_id}")
async def websocket_route(websocket: WebSocket, ws_id: str):
    await websocket_endpoint(websocket,ws_id)