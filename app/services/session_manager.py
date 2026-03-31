import os
import logging
import time
from datetime import datetime
from slugify import slugify
from typing import Optional, Dict, Any

from ..models.entities import Project, Session, SessionEvent, Screenshot, QuickNote, AudioRecording, Issue
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
        self.active_issue: Optional[Issue] = None
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

    def get_next_revision_title(self, project: Project) -> str:
        """Returns the next suggested revision title with padding (e.g., rev-000001)."""
        last_rev = self.db.get_last_revision_number(project.project_id)
        next_rev = last_rev + 1
        return f"rev-{next_rev:06d}"

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

        # MANDATORY: Start initial issue automatically
        self.start_issue("Observaciones iniciales")
        
        return session

    def resume_session(self, session_id: str):
        """Resumes an existing session."""
        session = self.db.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        self.active_session = session
        self.session_start_time_unix = time.time()
        self.event_sequence = 0
        
        self._log_event("session_resumed")

        # Check for active issue, if none, start one
        issues = self.db.get_issues_by_session(session_id)
        active_issues = [i for i in issues if i.status == "active"]
        if active_issues:
            self.active_issue = active_issues[0]
        else:
            self.start_issue(f"Continuación de sesión - {datetime.now().strftime('%H:%M')}")

        return session

    def start_issue(self, title: str):
        """Starts a new issue within the active session."""
        if not self.active_session:
            return

        # If there's an active issue, stop it first
        if self.active_issue:
            self.stop_issue()
            
        issue = Issue(
            session_id=self.active_session.session_id,
            title=title,
            start_time=datetime.now().isoformat(),
            status="active"
        )
        self.db.save_issue(issue)
        self.active_issue = issue
        
        self._log_event("issue_started", {
            "issue_id": issue.issue_id,
            "title": title
        })
        return issue

    def stop_issue(self, auto_start_next: bool = True):
        """Stops the current active issue and optionally starts a new one."""
        if not self.active_issue:
            return
            
        # MANDATORY: Stop audio if recording
        if self.audio_recorder.is_recording:
            duration_s = self.audio_recorder.stop_recording()
            self._log_event("audio_stopped_by_issue_end", {"duration_s": duration_s})

        self.active_issue.end_time = datetime.now().isoformat()
        self.active_issue.status = "finished"
        self.db.save_issue(self.active_issue)
        
        self._log_event("issue_stopped", {
            "issue_id": self.active_issue.issue_id,
            "title": self.active_issue.title
        })
        
        stopped_issue = self.active_issue
        self.active_issue = None

        if auto_start_next:
            # Get next issue count
            issues = self.db.get_issues_by_session(self.active_session.session_id)
            next_num = len(issues) + 1
            self.start_issue(f"Issue borrador #{next_num}")

        return stopped_issue

    def toggle_audio_recording(self) -> bool:
        """Toggles audio recording. Returns True if now recording, False otherwise."""
        if not self.active_session:
            return False
            
        if self.audio_recorder.is_recording:
            duration_s = self.audio_recorder.stop_recording()
            self._log_event("audio_stopped", {"duration_s": duration_s})
            return False
        else:
            # Generate a unique filename for this segment
            timestamp = datetime.now().strftime("%H%M%S")
            issue_tag = f"_issue_{self.active_issue.issue_id[:8]}" if self.active_issue else ""
            filename = f"audio_{timestamp}{issue_tag}.wav"
            audio_path = os.path.join(self.active_session.storage_path, "raw", "audio", filename)
            
            self.audio_recorder.start_recording(audio_path)
            self._log_event("audio_started", {
                "file": f"raw/audio/{filename}",
                "issue_id": self.active_issue.issue_id if self.active_issue else None
            })
            return True

    def take_manual_screenshot(self, monitor_index: int = 1):
        """Takes a manual screenshot of a specific monitor and logs it."""
        if not self.active_session:
            return
            
        timestamp_ms = self._get_timestamp_ms()
        # Count existing screenshots to get next sequence
        screenshots_dir = os.path.join(self.active_session.storage_path, "raw", "screenshots")
        seq = sum(1 for f in os.listdir(screenshots_dir) if f.endswith(".png")) + 1
        
        issue_tag = f"_{self.active_issue.title[:10]}" if self.active_issue else ""
        filename = f"{seq:04d}{slugify(issue_tag)}.png"
        rel_path = f"raw/screenshots/{filename}"
        abs_path = os.path.join(self.active_session.storage_path, rel_path)
        
        self.screenshot_service.take_screenshot(abs_path, filename, monitor_index)
        
        event = self._log_event("screenshot_taken", {
            "file": rel_path,
            "timestamp_ms": timestamp_ms,
            "monitor_index": monitor_index,
            "issue_id": self.active_issue.issue_id if self.active_issue else None
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
            "timestamp_ms": timestamp_ms,
            "issue_id": self.active_issue.issue_id if self.active_issue else None
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
        """Finalizes the session, stops audio if recording, and generates manifests."""
        if not self.active_session:
            return
            
        # Stop Issue if active
        if self.active_issue:
            self.stop_issue()

        # Stop Audio if active
        duration_s = 0
        if self.audio_recorder.is_recording:
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
            "audio_dir": "raw/audio",
            "events_file": "events.ndjson",
            "screenshots_dir": "raw/screenshots",
            "notes_file": "raw/notes/quick_notes.ndjson",
            "segmentation_anchors": "Check events.ndjson for screenshot_taken, quick_note_added, audio_started, and issue_started"
        }
        self.fs.save_manifest(storage_path, "llm_handoff_manifest", handoff_manifest)
        
        # README
        self.fs.create_readme_session(storage_path, self.active_session, summary)
