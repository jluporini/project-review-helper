import os
import json
import logging
from typing import Dict, Any, List
from ..models.entities import Session, SessionEvent, Screenshot, QuickNote

class FileSystemPersistence:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def create_session_structure(self, storage_path: str):
        """Creates the session folder structure: raw, raw/audio, raw/screenshots, raw/notes, derived, logs."""
        subfolders = [
            "raw/audio",
            "raw/screenshots",
            "raw/notes",
            "derived",
            "logs"
        ]
        for folder in subfolders:
            path = os.path.join(storage_path, folder)
            if not os.path.exists(path):
                os.makedirs(path)
        
        # Create .gitkeep in derived
        with open(os.path.join(storage_path, "derived", ".gitkeep"), "w") as f:
            f.write("")

    def save_event(self, storage_path: str, event: SessionEvent):
        """Appends a session event to events.ndjson."""
        event_file = os.path.join(storage_path, "events.ndjson")
        with open(event_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def save_manifest(self, storage_path: str, manifest_name: str, data: Dict[str, Any]):
        """Saves a JSON manifest file (e.g., session_manifest.json)."""
        manifest_file = os.path.join(storage_path, f"{manifest_name}.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_quick_note(self, storage_path: str, note: QuickNote):
        """Appends a quick note to quick_notes.ndjson in raw/notes."""
        notes_file = os.path.join(storage_path, "raw", "notes", "quick_notes.ndjson")
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(note.to_dict()) + "\n")

    def create_readme_session(self, storage_path: str, session: Session, summary: Dict[str, Any]):
        """Generates README_SESSION.md with basic session information."""
        readme_file = os.path.join(storage_path, "README_SESSION.md")
        content = f"""# Sesión de Revisión: {session.title}

- **Proyecto:** {session.project_id}
- **Tipo de Revisión:** {session.review_type}
- **Tester:** {session.tester_name}
- **Inicio:** {session.start_time}
- **Fin:** {session.end_time}
- **Estado:** {session.status}

## Resumen de Evidencia
- **Audio:** raw/audio/session_audio.wav
- **Capturas:** {summary.get('screenshot_count', 0)} (en raw/screenshots/)
- **Notas:** {summary.get('note_count', 0)} (en raw/notes/quick_notes.ndjson)
- **Eventos:** events.ndjson

Este paquete está preparado para procesamiento posterior por LLM.
"""
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write(content)
