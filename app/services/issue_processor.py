import os
import json
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from slugify import slugify

# We'll use a lazy import for faster-whisper to not block startup if not installed yet
# but for the implementation we'll assume it's available.

class IssueProcessor:
    def __init__(self, db, fs):
        self.db = db
        self.fs = fs
        self.logger = logging.getLogger(__name__)
        self._model = None

    def _get_model(self):
        """Lazy load the whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel
            # Using 'tiny' for MVP speed and compatibility, can be configurable
            self.logger.info("Loading Whisper model (tiny)...")
            self._model = WhisperModel("tiny", device="cpu", compute_type="int8")
        return self._model

    def process_issue(self, issue_id: str, output_dir: str, progress_callback=None):
        """
        Processes a single issue: transcribes audio, builds timeline, and exports files.
        """
        def log_progress(msg):
            self.logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        log_progress("Iniciando procesamiento de issue...")
        
        # 1. Resolve structures
        from ..models.entities import Issue
        # Assuming we can get issue by ID from DB (need to ensure this method exists)
        # For now, let's assume we find it via session or direct query if we add get_issue
        # Actually, let's fetch it from the DB
        with self.db._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM issues WHERE issue_id = ?", (issue_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Issue {issue_id} not found")
            issue_data = dict(row)
            
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (issue_data['session_id'],))
            session_data = dict(cursor.fetchone())
            
            cursor = conn.execute("SELECT * FROM projects WHERE project_id = ?", (session_data['project_id'],))
            project_data = dict(cursor.fetchone())

        log_progress(f"Procesando: Proyecto {project_data['code']} | Sesión {session_data['title']} | {issue_data['title']}")

        # 2. Identify Evidence via events.ndjson
        session_path = session_data['storage_path']
        events_file = os.path.join(session_path, "events.ndjson")
        
        relevant_events = []
        if os.path.exists(events_file):
            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    evt = json.loads(line)
                    # Filter events for this issue
                    # Note: events payload contains issue_id
                    if evt.get("payload", {}).get("issue_id") == issue_id:
                        relevant_events.append(evt)
                    # Also include the issue_started event itself if it matches
                    elif evt.get("event_type") == "issue_started" and evt.get("payload", {}).get("issue_id") == issue_id:
                        relevant_events.append(evt)
                    elif evt.get("event_type") == "issue_stopped" and evt.get("payload", {}).get("issue_id") == issue_id:
                        relevant_events.append(evt)

        # 3. Separate assets
        notes = []
        screenshots = []
        audios = []
        
        for evt in relevant_events:
            etype = evt["event_type"]
            payload = evt["payload"]
            ts = evt["timestamp_ms_from_session_start"]
            
            if etype == "quick_note_added":
                notes.append({
                    "id": evt.get("event_id"),
                    "ts": ts,
                    "text": payload.get("text")
                })
            elif etype == "screenshot_taken":
                screenshots.append({
                    "id": evt.get("event_id"),
                    "ts": ts,
                    "original_path": os.path.join(session_path, payload.get("file")),
                    "filename": os.path.basename(payload.get("file"))
                })
            elif etype == "audio_started":
                audios.append({
                    "id": evt.get("event_id"),
                    "ts_start": ts,
                    "original_path": os.path.join(session_path, payload.get("file")),
                    "filename": os.path.basename(payload.get("file")),
                    "ts_end": None # To be filled by audio_stopped if found or estimate
                })
            elif etype == "audio_stopped":
                # Find matching audio start (last one without end)
                for a in reversed(audios):
                    if a["ts_end"] is None:
                        a["ts_end"] = ts
                        break

        # 4. Transcription
        log_progress(f"Transcribiendo {len(audios)} archivos de audio...")
        transcripts_info = []
        for i, audio in enumerate(audios):
            log_progress(f"Transcribiendo audio {i+1}/{len(audios)}: {audio['filename']}...")
            if not os.path.exists(audio["original_path"]):
                log_progress(f"ADVERTENCIA: Archivo no encontrado {audio['original_path']}")
                continue
                
            model = self._get_model()
            # Force language to Spanish to avoid misdetection
            segments, info = model.transcribe(audio["original_path"], beam_size=5, language="es")
            
            audio_segments = []
            full_text_parts = []
            for segment in segments:
                # absolute_ts = audio_start_ts + offset
                abs_start = audio["ts_start"] + int(segment.start * 1000)
                abs_end = audio["ts_start"] + int(segment.end * 1000)
                
                audio_segments.append({
                    "offset_start_sec": segment.start,
                    "offset_end_sec": segment.end,
                    "absolute_start_ts": abs_start,
                    "absolute_end_ts": abs_end,
                    "text": segment.text.strip()
                })
                full_text_parts.append(segment.text.strip())
            
            audio["transcript"] = {
                "full_text": " ".join(full_text_parts),
                "segments": audio_segments
            }

        # 5. Build Timeline
        log_progress("Construyendo timeline unificada...")
        timeline = []
        
        for n in notes:
            timeline.append({
                "type": "note",
                "ts": n["ts"],
                "note_id": n["id"],
                "text": n["text"]
            })
            
        for s in screenshots:
            timeline.append({
                "type": "screenshot",
                "ts": s["ts"],
                "screenshot_id": s["id"],
                "original_path": s["original_path"],
                "filename": s["filename"]
            })
            
        for a in audios:
            if "transcript" in a:
                for seg in a["transcript"]["segments"]:
                    timeline.append({
                        "type": "transcript_segment",
                        "ts": seg["absolute_start_ts"],
                        "audio_id": a["id"],
                        "offset_start_sec": seg["offset_start_sec"],
                        "offset_end_sec": seg["offset_end_sec"],
                        "text": seg["text"]
                    })

        # Sort by timestamp
        timeline.sort(key=lambda x: x["ts"])

        # 6. Export Assets (Images)
        log_progress("Copiando imágenes...")
        img_dir = os.path.join(output_dir, "img")
        os.makedirs(img_dir, exist_ok=True)
        
        base_prefix = f"project_{project_data['code']}__session_{slugify(session_data['title'])}__issue_{issue_id}"
        
        for i, s in enumerate(screenshots):
            ext = os.path.splitext(s["filename"])[1]
            export_filename = f"{base_prefix}__shot_{i+1:03d}{ext}"
            export_path = os.path.join(img_dir, export_filename)
            try:
                shutil.copy2(s["original_path"], export_path)
                s["exported_path"] = f"img/{export_filename}"
                # Update timeline entry too
                for item in timeline:
                    if item.get("screenshot_id") == s["id"]:
                        item["exported_path"] = s["exported_path"]
            except Exception as e:
                log_progress(f"Error copiando imagen {s['filename']}: {str(e)}")

        # 7. Generate JSON
        log_progress("Generando JSON canónico...")
        export_data = {
            "schema_version": "0.1",
            "generated_at": datetime.now().isoformat(),
            "source": {
                "app": "Review Capture Assist",
                "scope": "single_issue_export"
            },
            "project": project_data,
            "session": session_data,
            "issue": issue_data,
            "assets": {
                "notes": notes,
                "screenshots": screenshots,
                "audio": audios
            },
            "timeline": timeline
        }
        
        json_filename = f"{base_prefix}.json"
        with open(os.path.join(output_dir, json_filename), "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        # 8. Generate Markdown
        log_progress("Generando Markdown legible...")
        md_content = self._generate_markdown(export_data)
        md_filename = f"{base_prefix}.md"
        with open(os.path.join(output_dir, md_filename), "w", encoding="utf-8") as f:
            f.write(md_content)

        log_progress("Proceso finalizado con éxito.")
        return os.path.join(output_dir, json_filename)

    def _generate_markdown(self, data: Dict[str, Any]) -> str:
        p = data["project"]
        s = data["session"]
        i = data["issue"]
        
        lines = []
        lines.append(f"# Reporte de Issue: {i['title']}")
        lines.append("")
        lines.append(f"- **Proyecto:** {p['name']} ({p['code']})")
        lines.append(f"- **Sesión:** {s['title']}")
        lines.append(f"- **Issue ID:** {i['issue_id']}")
        lines.append(f"- **Generado el:** {data['generated_at']}")
        lines.append("")
        lines.append("## Timeline Unificada")
        lines.append("")
        
        for item in data["timeline"]:
            ts_sec = item["ts"] / 1000
            time_str = f"{int(ts_sec // 3600):02d}:{int((ts_sec % 3600) // 60):02d}:{int(ts_sec % 60):02d}"
            
            if item["type"] == "note":
                lines.append(f"> **[{time_str}] NOTA:** {item['text']}")
            elif item["type"] == "screenshot":
                lines.append(f"![Captura {time_str}]({item.get('exported_path', '')})")
                lines.append(f"*Captura a los {time_str}*")
            elif item["type"] == "transcript_segment":
                lines.append(f"**[{time_str}]** {item['text']}")
            lines.append("")

        # Dedicated Transcripts Section
        if data["assets"]["audio"]:
            lines.append("---")
            lines.append("## Transcripciones Completas")
            lines.append("")
            for audio in data["assets"]["audio"]:
                lines.append(f"### Archivo: {audio['filename']}")
                if "transcript" in audio and audio["transcript"]["full_text"]:
                    lines.append(audio["transcript"]["full_text"])
                else:
                    lines.append("*No se generó transcripción para este archivo.*")
                lines.append("")

        lines.append("---")
        lines.append("## Resumen de Evidencias")
        lines.append(f"- **Notas:** {len(data['assets']['notes'])}")
        lines.append(f"- **Capturas:** {len(data['assets']['screenshots'])}")
        lines.append(f"- **Segmentos de Audio:** {len(data['assets']['audio'])}")
        
        return "\n".join(lines)
