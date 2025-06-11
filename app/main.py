from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import uuid
from uuid import UUID
import asyncpg
from asyncpg import Connection
from asyncpg.pool import Pool
from fastapi import  Depends, FastAPI, File, Form, Query,UploadFile,HTTPException,Request
import cloudinary,os
from database import DATABASE_URL
from enums import ImageFormat
from schemas import CreateImage
from cloudinary.uploader import upload,destroy
from dotenv import load_dotenv
load_dotenv()



# 初期化（最初に一度だけ呼ぶ）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 前処理
    db_pool: Pool = await asyncpg.create_pool(DATABASE_URL) 
    app.state.db_pool = db_pool # fastapiのstateへ保持|poolはSQLへの接続を管理するオブジェクト

    print("✅ Connected to database")
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
    yield
    # 後処理
    await app.state.db_pool.close()
    print("🛑 Disconnected from database")

app = FastAPI(lifespan=lifespan)

cloudinary.config(
    cloud_name = str(os.getenv("CLOUDINARY_CLOUD_NAME")),
    api_key = str(os.getenv("CLOUDINARY_API_KEY")),
    api_secret = str(os.getenv("CLOUDINARY_API_SECRET"))
)
# ジェネレータ関数で共通化 依存性注入でconn取得部分を共通化
async def get_db_conn(request: Request) -> AsyncGenerator[Connection, None]:
    db_pool = request.app.state.db_pool
    async with db_pool.acquire() as conn:
        yield conn  # 非同期ジェネレータとして返す


@app.get("/db_api1/images")
async def get_images(user_id: Optional[UUID] = Query(None),format: Optional[ImageFormat] = Query(None),conn:Connection = Depends(get_db_conn)): # Optionalが型でNone or Value Queryが入力時の話
    # クエリパラメータから検索ワードに一致する画像データ取得
    clauses = []
    values=[]
    if user_id:
        clauses.append(f"user_id = ${len(values)+1}")
        values.append(user_id)
    if format:
        clauses.append(f"format = ${len(values)+1}")
        values.append(format)
    if clauses:
        query = "SELECT * FROM images WHERE "+ " AND ".join(clauses)
        # " AND ".join(clauses) clausesの中身をANDでつないで文字列に変換する
    else:
        query = "SELECT * FROM images"

    rows = await conn.fetch(query,*values)
    return [dict(row) for row in rows]

@app.post("/db_api/images")
async def create_image(user_id:uuid.UUID=Form(...),title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...),conn:Connection=Depends(get_db_conn)):
    # formリクエストを受けとって、cloudinaryにpubidをハッシュ化した画像をストア
    public_id = uuid.uuid4() # ストアする画像のUUID生成
    upload_contents = await image_file.read()
    try:
        # cloudinary操作
        
        upload_res = upload(upload_contents,resource_type="auto",public_id=str(public_id),overwrite=False) # I/Oだけど公式sdkが非同期対応していないそのうち自作する
        version = upload_res["version"]
        image_url =  upload_res["secure_url"]
        format = upload_res["format"]
        # db操作

        await conn.execute(
            "INSERT INTO images (public_id, user_id, format, title, description, version) VALUES ($1, $2, $3, $4, $5, $6)",
            public_id, user_id, format, title, description, version
        )
        
        # レスポンス
        schema:CreateImage = CreateImage(public_id=public_id,user_id=user_id,title=title,description=description,format=format,version=version)
        return {"image_url":image_url,"image":schema}
    
    except Exception as e:
        destroy(public_id=str(public_id)) # トランザクション中DBでエラーが発生した場合のロールバック
        raise HTTPException(status_code=500,detail=f"Database error: {e}")
    
@app.delete("/db_api/images/{image_id}")
async def delete_image(image_id:UUID,conn:Connection = Depends(get_db_conn)):
    
    # database 操作
    
    res = await conn.execute("DELETE FROM images WHERE public_id = $1",image_id)
    if res == "DELETE 0":
        raise HTTPException(status_code=404,detail="Image not found in database")
    
    # cloudinary操作
    destroy_res = destroy(str(image_id))
    if destroy_res.get("result") != "ok":
        raise HTTPException(status_code=500, detail="Failed to delete image from Cloudinary")
    
    return {"detail":"Image deleted successfully"}

