from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class RepositoryCreate(BaseModel):
    path: str
    is_url: bool = False

class RepositoryOut(BaseModel):
    id: int
    name: str
    path: str
    source_url: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class FindingOut(BaseModel):
    id: int
    source: str
    path: str
    kind: str
    category: str
    severity: str
    excerpt: str
    start: int
    end: int
    hint: Optional[str]
    class Config:
        from_attributes = True

class ScanOut(BaseModel):
    id: int
    repo_id: int
    target_path: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    class Config:
        from_attributes = True
