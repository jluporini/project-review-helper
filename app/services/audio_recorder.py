import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import os
import logging
from datetime import datetime

class AudioRecorder:
    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.file_path = ""
        self.stream = None
        self.audio_data = []
        self.logger = logging.getLogger(__name__)

    def start_recording(self, file_path: str):
        """Starts recording audio in a separate thread."""
        self.file_path = file_path
        self.audio_data = []
        self.is_recording = True
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self._audio_callback
        )
        self.stream.start()
        self.logger.info(f"Audio recording started: {file_path}")

    def _audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice to collect audio chunks."""
        if status:
            self.logger.warning(f"Audio status: {status}")
        if self.is_recording:
            self.audio_data.append(indata.copy())

    def stop_recording(self) -> float:
        """Stops recording and saves the file. Returns duration in seconds."""
        if not self.is_recording:
            return 0.0
            
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            
        if not self.audio_data:
            self.logger.warning("No audio data captured.")
            return 0.0
            
        # Concatenate and save
        full_audio = np.concatenate(self.audio_data, axis=0)
        sf.write(self.file_path, full_audio, self.sample_rate)
        
        duration = len(full_audio) / self.sample_rate
        self.logger.info(f"Audio recording stopped. Duration: {duration:.2f}s")
        return duration
