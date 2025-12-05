from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from asyncpg import Connection
import os

from database import get_db_conn
from schemas import DBUser, Token
from auth import auth_user, create_access_token, get_current_user

router = APIRouter(
    tags=["auth"]
)

# main.pyからインポート（循環インポートを避けるため、関数内でインポート）
def get_blacklist_functions():
    from main import add_token_to_blacklist, cleanup_expired_tokens
    return add_token_to_blacklist, cleanup_expired_tokens

@router.post("/login")
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

@router.post("/logout")  
async def logout_user(request: Request, response: Response):
    """ログアウト処理 - JWTトークンをブラックリストに追加"""
    add_token_to_blacklist, cleanup_expired_tokens = get_blacklist_functions()
    
    token = request.cookies.get("access_token")
    
    if token:
        # JWTをブラックリストに追加（有効期限付き）
        add_token_to_blacklist(token)
        print(f"トークンをブラックリストに追加: {token[:20]}...")
        
        # 期限切れトークンのクリーンアップ
        cleanup_expired_tokens()
    
    # クッキーをクリア
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="none",
        secure=True
    )
    
    return {"message": "ログアウトしました"}

@router.get("/me")
async def get_me(current_user:DBUser = Depends(get_current_user)):
    dict_current_user = current_user.model_dump()
    dict_current_user.pop("hashed_password",None)
    return dict_current_user
