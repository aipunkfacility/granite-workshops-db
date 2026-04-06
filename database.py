# database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, \
    DateTime, Text, JSON, ForeignKey, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import os
import yaml

Base = declarative_base()


class RawCompanyRow(Base):
    __tablename__ = "raw_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, index=True)
    source_url = Column(String, default="")
    name = Column(String, nullable=False)
    phones = Column(JSON, default=list)      # list[str]
    address_raw = Column(Text, default="")
    website = Column(String, nullable=True)
    emails = Column(JSON, default=list)      # list[str]
    geo = Column(String, nullable=True)      # "lat,lon"
    messengers = Column(JSON, default=dict)  # {"telegram": "...", "vk": "...", ...}
    scraped_at = Column(DateTime, default=datetime.now)
    city = Column(String, nullable=False, index=True)
    merged_into = Column(Integer, ForeignKey("companies.id"), nullable=True)


class CompanyRow(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merged_from = Column(JSON, default=list)   # list[int]
    name_best = Column(String, nullable=False)
    phones = Column(JSON, default=list)
    address = Column(Text, default="")
    website = Column(String, nullable=True)
    emails = Column(JSON, default=list)
    city = Column(String, nullable=False, index=True)
    messengers = Column(JSON, default=dict)  # {"telegram": "...", "vk": "...", ...}
    status = Column(String, default="raw", index=True)
    segment = Column(String, default="Не определено")
    needs_review = Column(Boolean, default=False)
    review_reason = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class EnrichedCompanyRow(Base):
    __tablename__ = "enriched_companies"

    id = Column(Integer, primary_key=True)  # Принудительно задаем тот же ID, что и в CompanyRow
    name = Column(String, nullable=False)
    phones = Column(JSON, default=list)
    address_raw = Column(Text, default="")
    website = Column(String, nullable=True)
    emails = Column(JSON, default=list)
    city = Column(String, nullable=False, index=True)
    
    # Обогащенные данные
    messengers = Column(JSON, default=dict)   # {"telegram": "...", "whatsapp": "..."}
    tg_trust = Column(JSON, default=dict)     # {"trust_score": 3, "has_avatar": True, ...}
    cms = Column(String, default="unknown")
    has_marquiz = Column(Boolean, default=False)
    is_network = Column(Boolean, default=False)
    
    # Результаты анализа
    crm_score = Column(Integer, default=0, index=True)
    segment = Column(String, default="D", index=True)
    
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phones": self.phones or [],
            "address_raw": self.address_raw,
            "website": self.website,
            "emails": self.emails or [],
            "city": self.city,
            "messengers": self.messengers or {},
            "tg_trust": self.tg_trust or {},
            "cms": self.cms,
            "has_marquiz": self.has_marquiz,
            "is_network": self.is_network,
            "crm_score": self.crm_score,
            "segment": self.segment
        }


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String, nullable=False, index=True)
    stage = Column(String, nullable=False)
    source = Column(String, nullable=True)
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    records_found = Column(Integer, default=0)
    records_errors = Column(Integer, default=0)
    status = Column(String, default="running")
    error_message = Column(Text, default="")


# ===== Синглтон для доступа к БД =====

class Database:
    def __init__(self, db_path: str = None, config_path: str = "config.yaml"):
        if not db_path:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            db_path = config.get("database", {}).get("path", "data/granite.db")
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # WAL-режим: параллельные записи из ThreadPoolExecutor без "database is locked"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Включаем WAL и busy_timeout на уровне подключения
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")  # 5 сек ожидания блокировки
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()
