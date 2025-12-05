from uuid import UUID
from fastapi import APIRouter, Depends, Form, HTTPException
from asyncpg import Connection
import asyncpg
import uuid
import hashlib
import re

from database import get_db_conn

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

@router.post("")
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

@router.get("")
async def get_users(conn:Connection = Depends(get_db_conn)):
    rows = await conn.fetch("SELECT * FROM users")
    users = [] 
    for row in rows: # password省く
        user_dict = dict(row)
        user_dict.pop("password",None)
        users.append(user_dict)
    
    return users

@router.get("/{user_uuid}")
async def get_user(user_uuid:UUID,conn:Connection = Depends(get_db_conn)):
    user_id = str(user_uuid)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1",user_id)
    if row is None:
        raise HTTPException(status_code=404,detail="User not found")
    user_dict = dict(row)
    user_dict.pop("password")
    return user_dict

@router.delete("/{user_uuid}")
async def delete_user(user_uuid:UUID,conn:Connection = Depends(get_db_conn)):
    user_id = str(user_uuid)
    res = await conn.execute("DELETE FROM users WHERE user_id = $1",user_id)
    command,count = res.split(" ")
    if int(count) == 0:
        raise HTTPException(status_code=404,detail="User not found")
    
    return {"message": "User deleted successfully"}
