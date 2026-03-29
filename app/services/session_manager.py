import os
import logging
import time
from datetime import datetime
from slugify import slugify
from typing import Optional, Dict, Any

from ..models.entities import Project, Session, SessionEvent, Screenshot, QuickNote, AudioRecording
from .audio_recorder import AudioRecorder
from .screenshot_service import ScreenshotService
from ..persistence.file_system import FileSystemPersistence
from ..persistence.sqlite_db import SQLiteDB

class SessionManager:
    def __init__(self, db: SQLiteDB):
        self.db = db
        self.fs = FileSystemPersistence()
        self.audio_recorder = AudioRecorder()
        self.screenshot_service = ScreenshotService()
        
        self.active_session: Optional[Session] = None
        self.session_start_time_unix: float = 0
        self.event_sequence: int = 0
        self.logger = logging.getLogger(__name__)

    def _get_timestamp_ms(self) -> int:
        """Calculates milliseconds since session start."""
        if self.session_start_time_unix == 0:
            return 0
        return int((time.time() - self.session_start_time_unix) * 1000)

    def _log_event(self, event_type: str, payload: Dict[str, Any] = None):
        """Creates and persists a session event."""
        if not self.active_session:
            return
            
        self.event_sequence += 1
        event = SessionEvent(
            session_id=self.active_session.session_id,
            event_type=event_type,
            timestamp_ms_from_session_start=self._get_timestamp_ms(),
            sequence_number=self.event_sequence,
            payload=payload or {}
        )
        self.fs.save_event(self.active_session.storage_path, event)
        return event

    def start_session(self, project: Project, title: str, tester: str):
        """Initializes and starts a new session."""
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        slug = slugify(title)
        folder_name = f"{timestamp_str}_{slug}"
        storage_path = os.path.join(project.default_storage_root, folder_name)
        
        session = Session(
            project_id=project.project_id,
            title=title,
            tester_name=tester,
            start_time=datetime.now().isoformat(),
            status="active",
            storage_path=storage_path
        )
        
        # Persistence
        self.fs.create_session_structure(storage_path)
        self.db.save_session(session)
        
        self.active_session = session
        self.session_start_time_unix = time.time()
        self.event_sequence = 0
        
        # Log initial event
        self._log_event("session_started", {
            "tester": tester,
            "title": title,
            "project_code": project.code
        })
        
        # Start Audio
        audio_path = os.path.join(storage_path, "raw", "audio", "session_audio.wav")
        self.audio_recorder.start_recording(audio_path)
        self._log_event("audio_started", {"file": "raw/audio/session_audio.wav"})
        
        return session

    def take_manual_screenshot(self):
        """Takes a manual screenshot and logs it."""
        if not self.active_session:
            return
            
        timestamp_ms = self._get_timestamp_ms()
        seq = sum(1 for f in os.listdir(os.path.join(self.active_session.storage_path, "raw", "screenshots")) if f.endswith(".png")) + 1
        filename = f"{seq:04d}.png"
        rel_path = f"raw/screenshots/{filename}"
        abs_path = os.path.join(self.active_session.storage_path, rel_path)
        
        self.screenshot_service.take_screenshot(abs_path, filename)
        
        event = self._log_event("screenshot_taken", {
            "file": rel_path,
            "timestamp_ms": timestamp_ms
        })
        
        screenshot = Screenshot(
            session_id=self.active_session.session_id,
            event_id=event.event_id,
            relative_file_path=rel_path,
            file_name=filename,
            timestamp_ms_from_session_start=timestamp_ms
        )
        return screenshot

    def add_quick_note(self, text: str):
        """Adds a quick note and logs it."""
        if not self.active_session:
            return
            
        timestamp_ms = self._get_timestamp_ms()
        event = self._log_event("quick_note_added", {
            "text": text,
            "timestamp_ms": timestamp_ms
        })
        
        note = QuickNote(
            session_id=self.active_session.session_id,
            event_id=event.event_id,
            text=text,
            timestamp_ms_from_session_start=timestamp_ms
        )
        self.fs.save_quick_note(self.active_session.storage_path, note)
        return note

    def stop_session(self):
        """Finalizes the session, stops audio, and generates manifests."""
        if not self.active_session:
            return
            
        # Stop Audio
        duration_s = self.audio_recorder.stop_recording()
        self._log_event("audio_stopped", {"duration_s": duration_s})
        
        # Update Session
        self.active_session.end_time = datetime.now().isoformat()
        self.active_session.status = "finished"
        self.db.save_session(self.active_session)
        
        # Generate Manifests
        self._generate_session_manifests(duration_s)
        
        self._log_event("session_finished")
        
        session = self.active_session
        self.active_session = None
        return session

    def _generate_session_manifests(self, audio_duration_s: float):
        """Generates all necessary JSON and MD manifests for the session."""
        storage_path = self.active_session.storage_path
        
        # Count evidence
        screenshot_count = len([f for f in os.listdir(os.path.join(storage_path, "raw", "screenshots")) if f.endswith(".png")])
        
        summary = {
            "screenshot_count": screenshot_count,
            "note_count": 0, # Should be counted from NDJSON for accuracy
            "audio_duration_s": audio_duration_s
        }
        
        # Manifests
        session_manifest = {
            "session_id": self.active_session.session_id,
            "project_id": self.active_session.project_id,
            "title": self.active_session.title,
            "start_time": self.active_session.start_time,
            "end_time": self.active_session.end_time,
            "structure_version": "0.1",
            "summary": summary
        }
        self.fs.save_manifest(storage_path, "session_manifest", session_manifest)
        
        # Handoff Manifest for LLM
        handoff_manifest = {
            "audio_file": "raw/audio/session_audio.wav",
            "events_file": "events.ndjson",
            "screenshots_dir": "raw/screenshots",
            "notes_file": "raw/notes/quick_notes.ndjson",
            "segmentation_anchors": "Check events.ndjson for screenshot_taken and quick_note_added"
        }
        self.fs.save_manifest(storage_path, "llm_handoff_manifest", handoff_manifest)
        
        # README
        self.fs.create_readme_session(storage_path, self.active_session, summary)
