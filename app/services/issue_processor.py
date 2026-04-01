import os
import json
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from slugify import slugify

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
            self.logger.info("Loading Whisper model (tiny)...")
            self._model = WhisperModel("tiny", device="cpu", compute_type="int8")
        return self._model

    def process_issue(self, issue_id: str, output_dir: str, progress_callback=None):
        def log_progress(msg):
            self.logger.info(msg)
            if progress_callback: progress_callback(msg)

        log_progress("Iniciando procesamiento de issue...")
        
        # 1. Fetch data from DB
        with self.db._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM issues WHERE issue_id = ?", (issue_id,))
            issue_data = dict(cursor.fetchone())
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (issue_data['session_id'],))
            session_data = dict(cursor.fetchone())
            cursor = conn.execute("SELECT * FROM projects WHERE project_id = ?", (session_data['project_id'],))
            project_data = dict(cursor.fetchone())

        log_progress(f"Procesando: {project_data['code']} | {session_data['title']} | {issue_data['title']}")

        # 2. Filter events
        session_path = session_data['storage_path']
        events_file = os.path.join(session_path, "events.ndjson")
        relevant_events = []
        if os.path.exists(events_file):
            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    evt = json.loads(line)
                    if evt.get("payload", {}).get("issue_id") == issue_id:
                        relevant_events.append(evt)

        # 3. Assets Identification
        notes, screenshots, audios = [], [], []
        for evt in relevant_events:
            etype, payload, ts = evt["event_type"], evt["payload"], evt["timestamp_ms_from_session_start"]
            if etype == "quick_note_added":
                notes.append({"id": evt.get("event_id"), "ts": ts, "text": payload.get("text")})
            elif etype == "screenshot_taken":
                screenshots.append({"id": evt.get("event_id"), "ts": ts, "original_path": os.path.join(session_path, payload.get("file")), "filename": os.path.basename(payload.get("file"))})
            elif etype == "audio_started":
                audios.append({"id": evt.get("event_id"), "ts_start": ts, "original_path": os.path.join(session_path, payload.get("file")), "filename": os.path.basename(payload.get("file")), "ts_end": None})
            elif etype == "audio_stopped":
                for a in reversed(audios):
                    if a["ts_end"] is None:
                        a["ts_end"] = ts
                        break

        # 4. Transcription (Force Spanish)
        log_progress(f"Transcribiendo {len(audios)} audios...")
        for i, audio in enumerate(audios):
            if not os.path.exists(audio["original_path"]): continue
            segments, _ = self._get_model().transcribe(audio["original_path"], beam_size=5, language="es")
            audio_segments = []
            full_parts = []
            for s in segments:
                audio_segments.append({
                    "absolute_start_ts": audio["ts_start"] + int(s.start * 1000),
                    "text": s.text.strip()
                })
                full_parts.append(s.text.strip())
            audio["transcript"] = {"full_text": " ".join(full_parts), "segments": audio_segments}

        # 5. Build Timeline
        timeline = []
        for n in notes: timeline.append({"type": "note", "ts": n["ts"], "text": n["text"]})
        for s in screenshots: timeline.append({"type": "screenshot", "ts": s["ts"], "id": s["id"], "path": s["original_path"]})
        for a in audios:
            if "transcript" in a:
                for seg in a["transcript"]["segments"]:
                    timeline.append({"type": "transcript", "ts": seg["absolute_start_ts"], "text": seg["text"]})
        timeline.sort(key=lambda x: x["ts"])

        # 6. Export Images
        img_dir = os.path.join(output_dir, "img")
        os.makedirs(img_dir, exist_ok=True)
        base_prefix = f"{project_data['code']}_{slugify(session_data['title'])}_{issue_id[:8]}"
        for i, s in enumerate(screenshots):
            ext = os.path.splitext(s["filename"])[1]
            export_name = f"{base_prefix}_shot_{i+1:03d}{ext}"
            shutil.copy2(s["original_path"], os.path.join(img_dir, export_name))
            s["exported_path"] = f"img/{export_name}"
            for item in timeline:
                if item.get("id") == s["id"]: item["exported_path"] = f"img/{export_name}"

        # 7. Generate Files
        export_data = {
            "generated_at": datetime.now().isoformat(),
            "project": project_data, "session": session_data, "issue": issue_data,
            "assets": {"notes": notes, "screenshots": screenshots, "audio": audios},
            "timeline": timeline
        }
        
        with open(os.path.join(output_dir, f"{base_prefix}.json"), "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        with open(os.path.join(output_dir, f"{base_prefix}.md"), "w", encoding="utf-8") as f:
            f.write(self._generate_markdown(export_data))
            
        with open(os.path.join(output_dir, f"{base_prefix}.html"), "w", encoding="utf-8") as f:
            f.write(self._generate_html(export_data))

        log_progress("Exportación finalizada.")
        return os.path.join(output_dir, f"{base_prefix}.html")

    def _generate_markdown(self, data):
        lines = [f"# Reporte: {data['issue']['title']}", "", f"- **Proyecto:** {data['project']['name']}", f"- **Sesión:** {data['session']['title']}", ""]
        for item in data["timeline"]:
            t = f"[{int(item['ts']/1000//60):02d}:{int(item['ts']/1000%60):02d}]"
            if item["type"] == "note": lines.append(f"> {t} **NOTA:** {item['text']}")
            elif item["type"] == "screenshot": lines.append(f"![{t}]({item['exported_path']})")
            elif item["type"] == "transcript": lines.append(f"{t} {item['text']}")
            lines.append("")
        return "\n".join(lines)

    def _generate_html(self, data):
        p, s, i = data["project"], data["session"], data["issue"]
        html = [
            "<html><head><meta charset='utf-8'><title>Reporte de Issue</title>",
            "<style>body{font-family:sans-serif;max-width:900px;margin:40px auto;line-height:1.6;color:#333;}",
            ".header{background:#f4f4f4;padding:20px;border-radius:8px;margin-bottom:30px;}",
            ".note{background:#2d2d2d;color:#ccc;padding:15px;font-family:monospace;border-radius:4px;margin:10px 0;border-left:5px solid #0d6efd;}",
            ".transcript{margin:10px 0;padding:5px 0;}",
            ".screenshot{margin:20px 0;text-align:center;}",
            ".screenshot img{max-width:100%;border:1px solid #ddd;border-radius:4px;box-shadow:0 2px 5px rgba(0,0,0,0.1);}",
            ".ts{color:#888;font-weight:bold;margin-right:10px;font-size:0.9em;}",
            "</style></head><body>",
            f"<div class='header'><h1>Issue: {i['title']}</h1>",
            f"<p><strong>Proyecto:</strong> {p['name']} ({p['code']})<br>",
            f"<strong>Sesión:</strong> {s['title']}<br>",
            f"<strong>Generado:</strong> {data['generated_at']}<br>",
            f"<strong>App:</strong> Review Capture Assist | <strong>Scope:</strong> Single Issue Export</p></div>",
            "<h2>Timeline</h2>"
        ]
        
        for item in data["timeline"]:
            ts_sec = item["ts"] / 1000
            t_str = f"{int(ts_sec//60):02d}:{int(ts_sec%60):02d}"
            if item["type"] == "transcript":
                html.append(f"<p class='transcript'><span class='ts'>[{t_str}]</span> {item['text']}</p>")
            elif item["type"] == "note":
                html.append(f"<div class='note'><strong>[{t_str}] NOTA:</strong><br>{item['text']}</div>")
            elif item["type"] == "screenshot":
                html.append(f"<div class='screenshot'><img src='{item['exported_path']}'><br><small class='ts'>Captura a los {t_str}</small></div>")
        
        html.append("</body></html>")
        return "\n".join(html)
