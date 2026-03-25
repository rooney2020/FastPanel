import os
import json
import zipfile
import threading
from pathlib import Path
from urllib.request import urlretrieve
from PyQt5.QtCore import QObject, pyqtSignal

_MODELS_DIR = os.path.join(Path.home(), ".fastpanel", "vosk-models")
_SAMPLE_RATE = 16000

_MODEL_NAME = "vosk-model-cn-0.22"
_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip"
_MODEL_SIZE = "1.2GB"


class SttEngine(QObject):
    model_ready = pyqtSignal()
    model_progress = pyqtSignal(int)
    model_error = pyqtSignal(str)
    partial_result = pyqtSignal(str)
    final_result = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._recognizer = None

    def model_path(self) -> str:
        return os.path.join(_MODELS_DIR, _MODEL_NAME)

    def is_model_available(self) -> bool:
        p = self.model_path()
        return os.path.isdir(p) and os.path.isfile(os.path.join(p, "conf", "model.conf"))

    def load_model(self) -> bool:
        if self._model is not None:
            return True
        if not self.is_model_available():
            return False
        try:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self._model = Model(self.model_path())
            return True
        except Exception as e:
            self.model_error.emit(f"加载模型失败: {e}")
            return False

    def unload_model(self):
        self._model = None
        self._recognizer = None

    def create_recognizer(self):
        if self._model is None and not self.load_model():
            return False
        try:
            from vosk import KaldiRecognizer
            self._recognizer = KaldiRecognizer(self._model, _SAMPLE_RATE)
            self._recognizer.SetWords(False)
            return True
        except Exception as e:
            self.model_error.emit(f"创建识别器失败: {e}")
            return False

    def feed_audio(self, data: bytes):
        if self._recognizer is None:
            return
        if self._recognizer.AcceptWaveform(data):
            result = json.loads(self._recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                self.final_result.emit(text)
        else:
            partial = json.loads(self._recognizer.PartialResult())
            text = partial.get("partial", "").strip()
            if text:
                self.partial_result.emit(text)

    def finalize(self) -> str:
        if self._recognizer is None:
            return ""
        result = json.loads(self._recognizer.FinalResult())
        self._recognizer = None
        return result.get("text", "").strip()

    def download_model(self):
        thread = threading.Thread(target=self._download_worker, daemon=True)
        thread.start()

    def _download_worker(self):
        os.makedirs(_MODELS_DIR, exist_ok=True)
        zip_path = os.path.join(_MODELS_DIR, f"{_MODEL_NAME}.zip")

        model_dir = os.path.join(_MODELS_DIR, _MODEL_NAME)
        if os.path.isdir(model_dir):
            import shutil
            shutil.rmtree(model_dir, ignore_errors=True)

        try:
            def _progress(block_num, block_size, total_size):
                if total_size > 0:
                    pct = min(int(block_num * block_size * 100 / total_size), 100)
                    self.model_progress.emit(pct)

            self.model_progress.emit(0)
            urlretrieve(_MODEL_URL, zip_path, reporthook=_progress)
            self.model_progress.emit(100)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(_MODELS_DIR)

            os.remove(zip_path)
            self._model = None
            self.model_ready.emit()
        except Exception as e:
            self.model_error.emit(f"下载模型失败: {e}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
