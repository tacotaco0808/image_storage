from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, Optional
import uuid
from uuid import UUID
import asyncpg
from asyncpg import Connection
from asyncpg.pool import Pool
from fastapi import  Depends, FastAPI, File, Form, Query,UploadFile,HTTPException,Request
import cloudinary,os
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from auth import auth_user, create_access_token, get_current_user
from database import DATABASE_URL
from enums import ImageFormat
from schemas import Image, Token
from cloudinary.uploader import upload,destroy
from dotenv import load_dotenv
from security import oauth2_scheme
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
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(os.getenv("FRONT_IP"))],
    allow_credentials=True,
    allow_methods=["*"],  # 全メソッド（GET, POSTなど）許可
    allow_headers=["*"],  # 全ヘッダー許可)
)
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


@app.get("/images")
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

@app.get("/image",response_model=Image)
async def get_image(public_id:UUID,conn:Connection = Depends(get_db_conn)):
    db_res = await conn.fetchrow("SELECT * FROM images WHERE public_id = $1",public_id)
    if db_res is None:
        raise HTTPException(status_code=404,detail="Image not found")
    return dict(db_res)


@app.post("/images")
async def create_image(user_id:uuid.UUID=Form(...),title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...),conn:Connection=Depends(get_db_conn),auth_res = Depends(get_current_user)):
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
        schema:Image =Image(public_id=public_id,user_id=user_id,title=title,description=description,format=format,version=version)
        return {"image_url":image_url,"image":schema}
    
    except Exception as e:
        destroy(public_id=str(public_id)) # トランザクション中DBでエラーが発生した場合のロールバック
        raise HTTPException(status_code=500,detail=f"Database error: {e}")
    
@app.delete("/images/{image_id}")
async def delete_image(image_id:UUID,conn:Connection = Depends(get_db_conn),auth_res = Depends(get_current_user)):
    
    # database 操作
    
    res = await conn.execute("DELETE FROM images WHERE public_id = $1",image_id)
    if res == "DELETE 0":
        raise HTTPException(status_code=404,detail="Image not found in database")
    
    # cloudinary操作
    destroy_res = destroy(str(image_id))
    if destroy_res.get("result") != "ok":
        raise HTTPException(status_code=500, detail="Failed to delete image from Cloudinary")
    
    return {"detail":"Image deleted successfully"}

@app.post("/login")
async def login_for_access_token(form_data:OAuth2PasswordRequestForm = Depends())->Token:
    # ログイン後トークンの作成
    user_uuid = UUID(os.getenv("USER_ID"))
    user = auth_user(user_id=user_uuid,user_name=form_data.username,password=form_data.password)
    if not user:
        raise HTTPException(status_code=401,detail="Incorrect username or password",headers={"WWW-Authenticate": "Bearer"})
    minutes = float(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or 30)
    access_token_expires = timedelta(minutes=minutes)
    access_token = create_access_token(
        data={"sub": user.user_name}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token,token_type="bearer")