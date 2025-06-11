from contextlib import asynccontextmanager
from typing import Optional
import uuid
from uuid import UUID
import asyncpg
from asyncpg.pool import Pool
from fastapi import  FastAPI, File, Form, Query,UploadFile,HTTPException,Request
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

@app.get("/db_api1/images")
async def get_images(request:Request,user_id: Optional[UUID] = Query(None),format: Optional[ImageFormat] = Query(None)): # Optionalが型でNone or Value Queryが入力時の話
    # クエリパラメータから検索ワードに一致する画像データ取得
    db_pool:Pool = request.app.state.db_pool
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

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *values)
        return [dict(row) for row in rows]

@app.post("/db_api/images")
async def create_image(request:Request,user_id:uuid.UUID=Form(...),title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...)):
    # formリクエストを受けとって、cloudinaryにpubidをハッシュ化した画像をストア
    public_id = str(uuid.uuid4()) # ストアする画像のUUID生成
    upload_contents = await image_file.read()
    try:
        # cloudinary操作
        
        upload_res = upload(upload_contents,resource_type="auto",public_id=public_id) # I/Oだけど公式sdkが非同期対応していないそのうち自作する
        version = upload_res["version"]
        image_url =  upload_res["secure_url"]
        format = upload_res["format"]
        # db操作

        db_pool:Pool = request.app.state.db_pool
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO images (public_id, user_id, format, title, description, version) VALUES ($1, $2, $3, $4, $5, $6)",
                public_id, user_id, format, title, description, version
            )
        
        # レスポンス
        schema:CreateImage = CreateImage(user_id=user_id,title=title,description=description)
        return {"image_url":image_url,"image":schema}
    
    except Exception as e:
        try:
            destroy(public_id=public_id) # トランザクション中DBでエラーが発生した場合のロールバック
        except Exception as destroy_err:
            print(f"Failed to delete image from Cloudinary: {destroy_err}")
        raise HTTPException(status_code=400,detail=str(e))
    
# @app.post("/db_api/images")
# async def create_image(user_id:uuid.UUID=Form(...),title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...),db = Depends(get_db)):
#     # formリクエストを受けとって、cloudinaryにpubidをハッシュ化した画像をストア
#     upload_contents = await image_file.read()
#     try:
#         public_id = str(uuid.uuid4()) # ランダムなuuid生成
#         upload_res = upload(upload_contents,resource_type="auto",public_id=public_id)
#         version = upload_res["version"]
#         image_url =  upload_res["secure_url"]
#         format = upload_res["format"]
#         schema:CreateImage = CreateImage(user_id=user_id,title=title,description=description)
#         image = Image(public_id=public_id,user_id=schema.user_id,format=format,title=schema.title,description=schema.description,version=version)
#         db.add(image)
#         db.commit()
#         db.refresh(image)
#         return {
#                 "image_url":image_url,
#                 "image":image

#         }
#     except Exception as e:
#         raise HTTPException(status_code=400,detail=str(e))

# @app.delete("/db_api/images/{image_id}")
# async def delete_image(image_id:UUID,db:Session = Depends(get_db)):
#     # dbから画像取得
#     image = db.query(Image).filter(Image.public_id == str(image_id)).first()
#     if not image:
#         raise HTTPException(status_code=404,detail="Image not found")
#     # cloudinaryから削除
#     destroy_res = destroy(str(image_id))
#     if destroy_res.get("result") != "ok":
#         raise HTTPException(status_code=500,detail="Failed to delete image from Cloudinary")
#     # dbから削除
#     db.delete(image)
#     db.commit()

#     return {"detail": "Image deleted successfully"}