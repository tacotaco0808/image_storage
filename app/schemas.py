from uuid import UUID
from pydantic import BaseModel

class CreateImage(BaseModel):
    user_id: UUID
    title:str 
    description:str
    class Config:
        from_attributes = True


 

