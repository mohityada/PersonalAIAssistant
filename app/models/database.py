"""SQLAlchemy ORM models for the Personal AI Assistant."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    api_key_hash = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    files = relationship("File", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    file_type = Column(String(20), nullable=False, index=True)  # text, pdf, docx, image, md, etc.
    file_path = Column(String(500), nullable=False)  # S3 key
    original_filename = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="processing", server_default="processing")
    error_message = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    objects = Column(JSON, nullable=True)  # Detected objects for images
    location = Column(String(255), nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<File {self.original_filename} ({self.file_type})>"


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    vector_id = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    chunk_index = Column(Integer, nullable=False)
    source = Column(String(20), nullable=True)  # "text", "ocr", "caption"

    file = relationship("File", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk {self.file_id}:{self.chunk_index}>"
