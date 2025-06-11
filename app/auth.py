from datetime import datetime, timedelta, timezone
import os
from fastapi import Depends, HTTPException
from jose import jwt,JWTError
from typing import Union
from uuid import UUID
from schemas import TokenData, User
from security import oauth2_scheme

def auth_user(user_id:UUID,user_name:str,password:str):   
    if user_name != os.getenv("USER_NAME"):
        return False
    if password != os.getenv("PASSWORD"):
        return False
    
    
    user:User = User(user_id=user_id,user_name=user_name,hashed_password=password)
    return user

def create_access_token(data:dict ,expires_delta:Union[timedelta,None]=None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    # 環境変数の取得とチェック
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")   
    if not SECRET_KEY or not ALGORITHM:
        raise RuntimeError("SECRET_KEYとALGORITHMの環境変数が設定されていません")
    
    to_encode.update({"exp":expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # 環境変数の取得とチェック
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")   
    if not SECRET_KEY or not ALGORITHM:
        raise RuntimeError("SECRET_KEYとALGORITHMの環境変数が設定されていません")
    try:
        payload = jwt.decode(token,SECRET_KEY,[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)   
    except JWTError:
        raise credentials_exception
    
    if token_data.username != os.getenv("USER_NAME"):
            raise credentials_exception
    return "ok"
    
    