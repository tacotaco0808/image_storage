from datetime import datetime, timedelta, timezone
import hashlib
import os
from asyncpg import Connection
from fastapi import Depends, HTTPException
from jose import jwt,JWTError
from typing import Union
from database import get_db_conn
from schemas import TokenData, User
from security import oauth2_scheme

async def auth_user(login_id:str,password:str,conn:Connection):   
    '''
    ユーザを探してpasswordがあっているかどうかの認証
    '''
    row = await conn.fetchrow("SELECT * FROM users WHERE login_id = $1",login_id)
    if row is None:
        raise HTTPException(status_code=404,detail="User not found")
    
    if login_id != row["login_id"]:
        return False
    
    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    if hashed_input != row["password"]:
        return False
    
    
    user:User = User(user_id=row["user_id"],login_id=row["login_id"],user_name=row["name"])
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

async def get_current_user(token: str = Depends(oauth2_scheme),conn: Connection = Depends(get_db_conn) ):
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
    
    row = await conn.fetchrow("SELECT * FROM users WHERE login_id = $1",username)
    if token_data.username != os.getenv("USER_NAME"):
            raise credentials_exception
    return "ok"
    
    