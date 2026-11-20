from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class Item(Base):
    """
    Przykładowy uniwersalny model w bazie.
    Zmień pola na potrzeby tematu zadania (np. Portfolio, Trade, User, Sentiment, Alert).
    """
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    category = Column(String(50), default="General")
    value = Column(Float, default=0.0)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
