# backend/models/wallet.py

from sqlalchemy import Column, Integer, ForeignKey
from .database import Base

class Wallet(Base):
    __tablename__ = "wallet"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer)
    balance = Column(Integer, default=0)
