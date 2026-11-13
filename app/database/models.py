from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint
)

from app.database.db import Base


# Every table carries org_id, so each query can be scoped to one
# organization. Permission checks live in app/auth/permissions.py.


class Organization(Base):

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)  # login name
    password_hash = Column(String, nullable=False)   # bcrypt, never plain text
    role = Column(String, nullable=False)            # see app/auth/permissions.py
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=True, nullable=False)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_at = Column(DateTime)                     # set after too many failures
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)


class Scan(Base):
    """One screening session: the JD and every resume screened
    against it (re-runs after adding resumes update the same scan)."""

    __tablename__ = "scans"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    jd_text = Column(Text, nullable=False)
    resume_count = Column(Integer, default=0)
    shortlisted_count = Column(Integer, default=0)
    weights = Column(JSON)                           # criteria weights + signals
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ScanResult(Base):
    """One candidate's extracted result in a scan - no resume file
    or full resume text is stored."""

    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, index=True)
    rank = Column(Integer)                           # display order in the scan
    candidate_name = Column(String)
    email = Column(String)
    phone = Column(String)
    score = Column(Float)
    decision = Column(String)
    shortlisted = Column(Boolean, default=False)
    result = Column(JSON)                            # evaluation + parsed profile


class OrgLlmSetting(Base):
    """An org's chosen models (LiteLLM names). Orgs without a row use
    the defaults in app/llm_config.py. Never holds keys."""

    __tablename__ = "org_llm_settings"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True)
    model = Column(String, nullable=False)
    fallback_model = Column(String)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.utcnow)


class OrgApiKey(Base):
    """An org's own key for one AI provider, encrypted (see
    services/llm_settings_service.py). Write-only: only the last 4
    characters are ever shown."""

    __tablename__ = "org_api_keys"
    __table_args__ = (UniqueConstraint("org_id", "provider"),)

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    last4 = Column(String)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.utcnow)


class AgentLog(Base):

    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, index=True)             # empty for pre-login events
    user_id = Column(Integer)
    session_id = Column(String)
    agent_name = Column(String)
    event_type = Column(String)
    data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
