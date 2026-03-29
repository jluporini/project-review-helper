import mss
import os
import logging
from datetime import datetime

class ScreenshotService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_monitors(self) -> list:
        """Returns a list of available monitors."""
        with mss.mss() as sct:
            return sct.monitors

    def take_screenshot(self, storage_path: str, filename: str, monitor_index: int = 1) -> str:
        """Captures the specified monitor and saves it to the specified path."""
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            
            with mss.mss() as sct:
                # Capture the specified monitor and save it
                if monitor_index < 0 or monitor_index >= len(sct.monitors):
                    monitor_index = 1
                
                sct.shot(mon=monitor_index, output=storage_path)
                
            self.logger.info(f"Screenshot taken (mon={monitor_index}): {storage_path}")
            return storage_path
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {str(e)}")
            raise e
