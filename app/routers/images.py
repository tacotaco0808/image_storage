from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from asyncpg import Connection
import uuid
import os
from cloudinary.uploader import upload, destroy

from database import get_db_conn
from schemas import DBUser, Image
from auth import get_current_user
from enums import ImageFormat

router = APIRouter(
    prefix="/images",
    tags=["images"]
)

@router.get("")
async def get_images(user_id: Optional[UUID] = Query(None),format: Optional[ImageFormat] = Query(None),limit: Optional[int] = Query(None),offset: Optional[int] = Query(None),conn:Connection = Depends(get_db_conn)): # Optionalが型でNone or Value Queryが入力時の話
    # クエリパラメータから検索ワードに一致する画像データ取得
    clauses = []
    values=[]
    if user_id:
        clauses.append(f"user_id = ${len(values)+1}")
        values.append(user_id)
    if format:
        clauses.append(f"format = ${len(values)+1}")
        values.append(format)
    
    # WHERE句の構築
    where_clause = ""
    if clauses:
        where_clause = "WHERE " + " AND ".join(clauses)
    
    # 総数を取得するクエリ
    count_query = f"SELECT COUNT(*) FROM images {where_clause}"
    total_count = await conn.fetchval(count_query, *values)
    
    # データを取得するクエリ
    query = f"SELECT * FROM images {where_clause} ORDER BY created_at DESC"
    
    if limit is not None:
        query += f" LIMIT ${len(values)+1}"
        values.append(limit)
    
    if offset is not None:
        query += f" OFFSET ${len(values)+1}"
        values.append(offset)

    rows = await conn.fetch(query,*values)
    images = [dict(row) for row in rows]
    
    # 総数と画像データを返す
    return {
        "images": images,
        "total": total_count,
        "count": len(images)
    }

@router.get("/{image_id}")  # response_modelを削除
async def get_image_by_id(image_id: UUID, conn: Connection = Depends(get_db_conn)):
    """特定の画像のメタデータを取得"""
    db_res = await conn.fetchrow("SELECT * FROM images WHERE public_id = $1", image_id)
    if db_res is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image_dict = dict(db_res)
    
    # Cloudinaryの画像URLを生成
    cloudinary_url = f"https://res.cloudinary.com/{os.getenv('CLOUDINARY_CLOUD_NAME')}/image/upload/v{image_dict['version']}/{image_dict['public_id']}.{image_dict['format']}"
    
    return {
        **image_dict,
        "image_url": cloudinary_url
    }

@router.post("")
async def create_image(title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...),conn:Connection=Depends(get_db_conn),current_user:DBUser = Depends(get_current_user)):
    # formリクエストを受けとって、cloudinaryにpubidをハッシュ化した画像をストア
    public_id = uuid.uuid4() # ストアする画像のUUID生成
    upload_contents = await image_file.read()
    user_id = current_user.user_id
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
    
@router.delete("/{image_id}")
async def delete_image(image_id:UUID,conn:Connection = Depends(get_db_conn),current_user:DBUser = Depends(get_current_user)):
    
    # database 操作
    row = await conn.fetchrow("SELECT * FROM images WHERE public_id = $1",image_id)
    if row is None:
        raise HTTPException(status_code=404,detail="Image not found")
    
    dict_row = dict(row)
    if dict_row["user_id"] != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to perform this action"
        )
    
    res = await conn.execute("DELETE FROM images WHERE public_id = $1",image_id)
    if res == "DELETE 0":
        raise HTTPException(status_code=404,detail="Image not found in database")
    
    # cloudinary操作
    destroy_res = destroy(str(image_id))
    if destroy_res.get("result") != "ok":
        raise HTTPException(status_code=500, detail="Failed to delete image from Cloudinary")
    
    return {"detail":"Image deleted successfully"}
