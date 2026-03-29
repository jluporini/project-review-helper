from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

@dataclass
class Project:
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = ""
    name: str = ""
    description: str = ""
    default_storage_root: str = ""
    session_subpath_pattern: str = "{YYYY}-{MM}-{DD}_{HHmmss}_{slug}"
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    title: str = ""
    description: str = ""
    review_type: str = "functional"
    tester_name: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: str = "created"  # created, active, finished, error
    storage_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

@dataclass
class SessionEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_type: str = ""  # session_started, audio_started, screenshot_taken, quick_note_added, etc.
    timestamp_absolute: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_ms_from_session_start: int = 0
    sequence_number: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

@dataclass
class Screenshot:
    screenshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""
    relative_file_path: str = ""
    file_name: str = ""
    timestamp_ms_from_session_start: int = 0
    timestamp_absolute: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

@dataclass
class QuickNote:
    note_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""
    text: str = ""
    timestamp_ms_from_session_start: int = 0
    timestamp_absolute: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

@dataclass
class AudioRecording:
    audio_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    file_path: str = ""
    format: str = "wav"
    sample_rate: int = 44100
    channels: int = 1
    duration_ms: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)
