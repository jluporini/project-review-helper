import unittest
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
from app.services.session_manager import SessionManager
from app.persistence.sqlite_db import SQLiteDB
from app.models.entities import Project

class TestSession(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = SQLiteDB(self.db_path)
        
        # Mock services that interact with hardware
        self.patcher_audio = patch('app.services.audio_recorder.sd.InputStream')
        self.patcher_sf = patch('app.services.audio_recorder.sf.write')
        self.patcher_mss = patch('app.services.screenshot_service.mss.mss')
        
        self.mock_audio = self.patcher_audio.start()
        self.mock_sf = self.patcher_sf.start()
        self.mock_mss = self.patcher_mss.start()
        
        self.manager = SessionManager(self.db)

    def tearDown(self):
        self.patcher_audio.stop()
        self.patcher_sf.stop()
        self.patcher_mss.stop()
        
        # Explicitly delete objects that might hold DB connections
        del self.manager
        del self.db
        
        # Small delay to let Windows release file locks
        import gc
        gc.collect()
        
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            # Fallback if Windows still locks it
            import time
            time.sleep(0.5)
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_session_flow(self):
        # 1. Create Project
        project = Project(
            name="Test Proj", 
            code="test", 
            default_storage_root=os.path.join(self.test_dir, "storage")
        )
        self.db.save_project(project)
        
        # 2. Start Session
        session = self.manager.start_session(project, "Session 1", "Tester")
        self.assertTrue(os.path.exists(session.storage_path))
        self.assertTrue(os.path.exists(os.path.join(session.storage_path, "events.ndjson")))
        
        # 3. Take Screenshot
        self.manager.take_manual_screenshot()
        # Verify event was logged (we'd need to read the file to be sure)
        
        # 4. Add Note
        self.manager.add_quick_note("This is a test note")
        
        # 5. Stop Session
        self.manager.stop_session()
        
        # Verify Manifests
        self.assertTrue(os.path.exists(os.path.join(session.storage_path, "session_manifest.json")))
        self.assertTrue(os.path.exists(os.path.join(session.storage_path, "llm_handoff_manifest.json")))
        self.assertTrue(os.path.exists(os.path.join(session.storage_path, "README_SESSION.md")))

if __name__ == "__main__":
    unittest.main()
