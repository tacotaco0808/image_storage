from typing import Union
from uuid import UUID
from pydantic import BaseModel

class Image(BaseModel):
    public_id:UUID
    user_id: UUID
    title:str 
    description:str
    format: str
    version:int

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token:str
    token_type:str

class TokenData(BaseModel):
    username: Union[str, None] = None

class User(BaseModel):
    user_id:UUID
    user_name:str
    hashed_password:str
