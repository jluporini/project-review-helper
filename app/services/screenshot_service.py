import mss
import os
import logging
from datetime import datetime

class ScreenshotService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def take_screenshot(self, storage_path: str, filename: str) -> str:
        """Captures the primary monitor and saves it to the specified path."""
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            
            with mss.mss() as sct:
                # Capture the primary monitor (mon=1) and save it
                screenshot = sct.shot(mon=1, output=storage_path)
                
            self.logger.info(f"Screenshot taken: {storage_path}")
            return storage_path
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {str(e)}")
            raise e
