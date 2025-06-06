from sqlalchemy import  Column, DateTime, Integer, String
from database import Base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
class Image(Base):
    __tablename__ = "images"

    public_id = Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True))
    version = Column(Integer,nullable=False)
    title = Column(String)
    description = Column(String)
    created_at = Column(DateTime(timezone=True),nullable=False,default=lambda: datetime.now(timezone.utc))