from typing import Optional
import uuid
from uuid import UUID
from fastapi import Depends, FastAPI, File, Form, Query,UploadFile,HTTPException
import cloudinary,os
from database import Base, SessionLocal,engine
from enums import ImageFormat
from models import Image
from schemas import CreateImage
from sqlalchemy.orm import Session
from cloudinary.uploader import upload,destroy
from dotenv import load_dotenv
load_dotenv()


def get_db(): #データベースを開いて閉じる部分の共通化
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()
Base.metadata.create_all(bind=engine)
cloudinary.config(
    cloud_name = str(os.getenv("CLOUDINARY_CLOUD_NAME")),
    api_key = str(os.getenv("CLOUDINARY_API_KEY")),
    api_secret = str(os.getenv("CLOUDINARY_API_SECRET"))
)

@app.get("/db_api1/images")
async def get_images(user_id: Optional[UUID] = Query(None),format: Optional[ImageFormat] = Query(None),db:Session = Depends(get_db)): # Optionalが型でNone or Value Queryが入力時の話
    # クエリパラメータから検索ワードに一致する画像データ取得
    query = db.query(Image)
    if user_id is not None:
        query = query.filter(Image.user_id == user_id)
    if format is not None:
        query = query.filter(Image.format == format)

    return query.all()
@app.post("/db_api/images")
async def create_image(user_id:uuid.UUID=Form(...),title:str = Form(...),description:str = Form(...),image_file:UploadFile=File(...),db = Depends(get_db)):
    # formリクエストを受けとって、cloudinaryにpubidをハッシュ化した画像をストア
    upload_contents = await image_file.read()
    try:
        public_id = str(uuid.uuid4()) # ランダムなuuid生成
        upload_res = upload(upload_contents,resource_type="auto",public_id=public_id)
        version = upload_res["version"]
        image_url =  upload_res["secure_url"]
        format = upload_res["format"]
        schema:CreateImage = CreateImage(user_id=user_id,title=title,description=description)
        image = Image(public_id=public_id,user_id=schema.user_id,format=format,title=schema.title,description=schema.description,version=version)
        db.add(image)
        db.commit()
        db.refresh(image)
        return {
                "image_url":image_url,
                "image":image

        }
    except Exception as e:
        raise HTTPException(status_code=400,detail=str(e))

@app.delete("/db_api/images/{image_id}")
async def delete_image(image_id:UUID,db:Session = Depends(get_db)):
    # dbから画像取得
    image = db.query(Image).filter(Image.public_id == str(image_id)).first()
    if not image:
        raise HTTPException(status_code=404,detail="Image not found")
    # cloudinaryから削除
    destroy_res = destroy(str(image_id))
    if destroy_res.get("result") != "ok":
        raise HTTPException(status_code=500,detail="Failed to delete image from Cloudinary")
    # dbから削除
    db.delete(image)
    db.commit()

    return {"detail": "Image deleted successfully"}