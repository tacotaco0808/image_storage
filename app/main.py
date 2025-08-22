import asyncio
import json
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import  Optional
import uuid
from uuid import UUID
import asyncpg
from asyncpg import Connection
from asyncpg.pool import Pool
from fastapi import  Depends, FastAPI, File, Form, Query, Response,UploadFile,HTTPException, WebSocket, WebSocketDisconnect
import cloudinary,os
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.websockets import WebSocketState
from auth import auth_user, create_access_token, get_current_user,get_current_user_ws
from database import DATABASE_URL, get_db_conn
from enums import ImageFormat
from eventHandler import EventHandler
from schemas import DBUser, Image, Token, User
from cloudinary.uploader import upload,destroy
from dotenv import load_dotenv
from security import oauth2_scheme
import hashlib
import re

from websocket import ConnectionManager
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
    await app.state.db_pool.close()
    print("🛑 Disconnected from database")


app = FastAPI(lifespan=lifespan,root_path="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(os.getenv("FRONT_IP")),"http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],  # 全メソッド（GET, POSTなど）許可
    allow_headers=["*"],  # 全ヘッダー許可)
)
cloudinary.config(
    cloud_name = str(os.getenv("CLOUDINARY_CLOUD_NAME")),
    api_key = str(os.getenv("CLOUDINARY_API_KEY")),
    api_secret = str(os.getenv("CLOUDINARY_API_SECRET"))
)

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
    
@app.delete("/images/{image_id}")
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

@app.post("/users")
async def create_user(name:str = Form(...),login_id:str=Form(...),password:str = Form(...),conn:Connection = Depends(get_db_conn)):
    user_id = uuid.uuid4() # ユーザのUUIDを作成
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    if not re.fullmatch(r"^[a-zA-Z0-9_]+$",login_id): # login_id は半角英数字のみに限定
        raise HTTPException(status_code=400,detail="login_id must contain only half-width letters, numbers, and underscores")
    try:
        res = await conn.execute("INSERT INTO users (user_id,name,login_id,password) VALUES ($1,$2,$3,$4)",user_id,name,login_id,hashed_password)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409,detail="This login_id is already in use")

    return {"user_id":user_id,"name":name,"login_id":login_id,"message":"User created successfully"}

@app.get("/users")
async def get_users(conn:Connection = Depends(get_db_conn)):
    rows = await conn.fetch("SELECT * FROM users")
    users = [] 
    for row in rows: # password省く
        user_dict = dict(row)
        user_dict.pop("password",None)
        users.append(user_dict)
    
    return users

@app.get("/users/{user_uuid}")
async def get_user(user_uuid:UUID,conn:Connection = Depends(get_db_conn)):
    user_id = str(user_uuid)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1",user_id)
    if row is None:
        raise HTTPException(status_code=404,detail="User not found")
    user_dict = dict(row)
    user_dict.pop("password")
    return user_dict

@app.delete("/users/{user_uuid}")
async def delete_user(user_uuid:UUID,conn:Connection = Depends(get_db_conn)):
    user_id = str(user_uuid)
    res = await conn.execute("DELETE FROM users WHERE user_id = $1",user_id)
    command,count = res.split(" ")
    if int(count) == 0:
        raise HTTPException(status_code=404,detail="User not found")
    
    return {"message": "User deleted successfully"}

@app.post("/login")
async def login_for_access_token(res:Response,form_data:OAuth2PasswordRequestForm = Depends(),conn:Connection=Depends(get_db_conn)):
    # ログイン後トークンの作成
    user= await auth_user(login_id=form_data.username,password=form_data.password,conn=conn)
    if not user:
        raise HTTPException(status_code=401,detail="Incorrect username or password",headers={"WWW-Authenticate": "Bearer"})
    minutes = float(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or 30)
    access_token_expires = timedelta(minutes=minutes)
    access_token = create_access_token(
        data={"sub": user.login_id}, expires_delta=access_token_expires
    )
    token = Token(access_token=access_token,token_type="bearer")
    res.set_cookie(key="access_token",
        value=token.access_token,
        httponly=True,
        secure=True,  # 本番では True (HTTPS)
        max_age=1800,
        samesite="none",
        path="/")
    return {"message":"Login successful"}

@app.get("/me")
async def get_me(current_user:DBUser = Depends(get_current_user)):
    dict_current_user = current_user.model_dump()
    dict_current_user.pop("hashed_password",None)
    return dict_current_user

wsmanager = ConnectionManager()

@app.websocket("/ws/{ws_id}")
async def websocket_endpoint(websocket:WebSocket,ws_id:str):
    # ws_idは接続してきたクライアントのID
    current_user = await get_current_user_ws(websocket,websocket.app)
    if not current_user:
        await websocket.close(code=4003, reason="Unauthorized")
        print(f"認証がありません")
        return 
    else:
        print(f"認証されています")
        print(f"currentuser:{current_user}")

 

    await wsmanager.addWebSocket(websocket,ws_id)
    # if not coccection_accepted:
    #     return 
    
    
    # すでにサーバに接続されているクライアントを今接続してきたクライアントの画面に反映する
    for user_id,ws in wsmanager.websockets.items():
        if not ws_id == user_id and not ws.client_state == WebSocketState.DISCONNECTED:
            await wsmanager.sendJson({"event":"login","player_id":user_id},ws_id,websocket)
            def message():
                text = ""
                for id,ws in wsmanager.websockets.items():
                    text += f"ウェブソケット:{id}:{ws.client_state}\n"
                return text
            # await wsmanager.sendMessage(websocket,f"{message()}")
    
    await wsmanager.broadCastJson({"event":"login","player_id":ws_id},ws_id)
    eventHandler = EventHandler(wsmanager)
    try:
        while(True):
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                print(f"From Client:{event}",flush=True)
                await eventHandler.handle(event=event,websocket=websocket,user_id=ws_id)

            except Exception as e:
                print(f"{e}")
            # await wsmanager.sendMessage(websocket,data)
            # await wsmanager.broadCastMessage(f"hello:{ws_id}")
            # await wsmanager.broadCastJson(event_type="position",user_id="aiueo",x=100,y=100)
            # 全部jsonで扱って、イベントの先頭で区別したほうがよさそう。"message","position"
    except WebSocketDisconnect:
        await wsmanager.broadCastJson({"event":"logout","player_id":ws_id},ws_id)
        await wsmanager.deleteWebSocket(websocket,ws_id)
    except RuntimeError:
        await wsmanager.broadCastJson({"event":"logout","player_id":ws_id},ws_id)
        await wsmanager.deleteWebSocket(websocket,ws_id)
    except Exception as e:
        await wsmanager.broadCastJson({"event":"logout","player_id":ws_id},ws_id)
        await wsmanager.deleteWebSocket(websocket,ws_id)
        
    # await websocket.accept()
    # while(True):
    #     data = await websocket.receive_text()
    #     print(f"From Client:{data}")
    #     await websocket.send_text(f"From Server:{data}")