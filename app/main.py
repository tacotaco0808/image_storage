from fastapi import Depends, FastAPI
import cloudinary,os
from database import Base, SessionLocal,engine
from models import Image
from schemas import CreateImage
def get_db(): #データベースを開いて閉じる部分の共通化
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()
Base.metadata.create_all(bind=engine)
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

@app.post("/db_api/images")
async def create_image(schema:CreateImage,db = Depends(get_db)):
    version = 123
    image = Image(user_id=schema.user_id,title=schema.title,description=schema.description,version=version)
    db.add(image)
    db.commit()
    db.refresh(image)

    return image
