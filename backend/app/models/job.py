"""
SQLAlchemy ORM models for Job tracking
"""
from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()


class Job(Base):
    """Job model - tracks video generation workflow"""
    __tablename__ = "jobs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    imdb_url = Column(String(255), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False, index=True)
    # Values: pending, metadata_extraction, script_generation, tts_subtitles,
    #         asset_gathering, video_composition, export, completed, failed, cancelled
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    error_message = Column(Text, nullable=True)
    failure_stage = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0)
    
    metadata_id = Column(String(36), ForeignKey("metadata.id"), nullable=True)
    output_video_path = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    
    # Relationships
    movie_metadata = relationship("Metadata", back_populates="jobs")
    execution_logs = relationship("JobExecutionLog", back_populates="job", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_status_created", "status", "created_at"),
        Index("idx_imdb_url", "imdb_url"),
    )
    
    def __repr__(self):
        return f"<Job {self.id}: {self.status}>"


class Metadata(Base):
    """Metadata model - IMDb cache"""
    __tablename__ = "metadata"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    imdb_id = Column(String(20), unique=True, nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    plot = Column(Text, nullable=False)
    runtime_minutes = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    release_year = Column(Integer, nullable=True)
    
    genres = Column(JSON, nullable=True)  # List of genres
    cast = Column(JSON, nullable=True)     # List of cast members
    directors = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)  # Extensible JSON
    
    poster_url = Column(String(255), nullable=True)
    trailer_url = Column(String(255), nullable=True)
    
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    refresh_count = Column(Integer, default=0)
    
    # Relationships
    jobs = relationship("Job", back_populates="movie_metadata")
    
    def __repr__(self):
        return f"<Metadata {self.imdb_id}: {self.title}>"


class JobExecutionLog(Base):
    """Execution log model - audit trail"""
    __tablename__ = "job_execution_log"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    stage = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # success, failed, retried
    
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    
    error_message = Column(Text, nullable=True)
    retry_attempt = Column(Integer, default=0)
    
    tokens_used = Column(Integer, nullable=True)
    api_call_cost_usd = Column(Float, nullable=True)
    
    job = relationship("Job", back_populates="execution_logs")
    
    __table_args__ = (
        Index("idx_job_stage", "job_id", "stage"),
        Index("idx_stage", "stage"),
    )
    
    def __repr__(self):
        return f"<ExecutionLog {self.job_id}: {self.stage} ({self.status})>"
