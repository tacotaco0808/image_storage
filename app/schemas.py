from uuid import UUID
from pydantic import BaseModel

class CreateImage(BaseModel):
    public_id:UUID
    user_id: UUID
    title:str 
    description:str
    format: str
    version:int

    class Config:
        from_attributes = True


 

