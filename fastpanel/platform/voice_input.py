import re
import sys
import subprocess
import threading

from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

from fastpanel.platform.stt import SttEngine, _SAMPLE_RATE


class VoiceState:
    IDLE = "idle"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    DOWNLOADING = "downloading"


class VoiceInputController(QObject):
    state_changed = pyqtSignal(str)
    partial_text = pyqtSignal(str)
    final_text = pyqtSignal(str)
    download_progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = VoiceState.IDLE
        self._stt = SttEngine(self)
        self._rec_proc: subprocess.Popen | None = None
        self._rec_thread: threading.Thread | None = None

        self._stt.partial_result.connect(self._on_partial)
        self._stt.final_result.connect(self._on_segment)
        self._stt.model_ready.connect(self._on_model_ready)
        self._stt.model_progress.connect(self._on_model_progress)
        self._stt.model_error.connect(self._on_model_error)

    @property
    def state(self) -> str:
        return self._state

    @property
    def stt_engine(self) -> SttEngine:
        return self._stt

    def toggle(self):
        if self._state == VoiceState.IDLE:
            self._try_start()
        elif self._state == VoiceState.RECORDING:
            self._stop_recording()

    def _try_start(self):
        if not self._check_vosk():
            self._set_state(VoiceState.DOWNLOADING)
            self._install_vosk()
            return

        if not self._stt.is_model_available():
            self._set_state(VoiceState.DOWNLOADING)
            self._stt.download_model()
            return

        self._start_recording()

    @staticmethod
    def _check_vosk() -> bool:
        try:
            import vosk  # noqa: F401
            return True
        except ImportError:
            return False

    def _install_vosk(self):
        self.download_progress.emit(0)
        thread = threading.Thread(target=self._install_worker, daemon=True)
        thread.start()

    def _install_worker(self):
        try:
            self.download_progress.emit(5)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "vosk"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                err = result.stderr.strip()[-200:]
                self.error.emit(f"安装 vosk 失败: {err}")
                self._set_state(VoiceState.IDLE)
                return
            self.download_progress.emit(30)

            if not self._stt.is_model_available():
                self._stt.download_model()
            else:
                self._on_model_ready()
        except Exception as e:
            self.error.emit(f"安装 vosk 失败: {e}")
            self._set_state(VoiceState.IDLE)

    def _on_model_ready(self):
        if self._state == VoiceState.DOWNLOADING:
            self._start_recording()

    def _on_model_progress(self, pct: int):
        adjusted = 30 + int(pct * 0.7)
        self.download_progress.emit(adjusted)

    def _on_model_error(self, msg: str):
        self._set_state(VoiceState.IDLE)
        self.error.emit(msg)

    def _start_recording(self):
        if not self._stt.load_model():
            self.error.emit("语音模型加载失败")
            self._set_state(VoiceState.IDLE)
            return

        if not self._stt.create_recognizer():
            self.error.emit("创建语音识别器失败")
            self._set_state(VoiceState.IDLE)
            return

        self._set_state(VoiceState.RECORDING)

        try:
            self._rec_proc = subprocess.Popen(
                ["arecord", "-f", "S16_LE", "-r", str(_SAMPLE_RATE),
                 "-c", "1", "-t", "raw", "-q", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self._rec_thread = threading.Thread(
                target=self._read_audio_loop, daemon=True
            )
            self._rec_thread.start()
        except FileNotFoundError:
            self._set_state(VoiceState.IDLE)
            self.error.emit("找不到 arecord，请安装: sudo apt install alsa-utils")
        except Exception as e:
            self._set_state(VoiceState.IDLE)
            self.error.emit(f"无法打开麦克风: {e}")

    def _read_audio_loop(self):
        CHUNK = 4000
        proc = self._rec_proc
        if proc is None or proc.stdout is None:
            return
        try:
            while self._state == VoiceState.RECORDING and proc.poll() is None:
                data = proc.stdout.read(CHUNK * 2)
                if not data:
                    break
                self._stt.feed_audio(data)
        except Exception:
            pass

    def _stop_recording(self):
        self._set_state(VoiceState.FINALIZING)

        if self._rec_proc is not None:
            try:
                self._rec_proc.terminate()
                self._rec_proc.wait(timeout=2)
            except Exception:
                try:
                    self._rec_proc.kill()
                except Exception:
                    pass
            self._rec_proc = None

        if self._rec_thread is not None:
            self._rec_thread.join(timeout=2)
            self._rec_thread = None

        remaining = self._stt.finalize()
        if remaining:
            remaining = self._clean_text(remaining)
            if remaining:
                self.final_text.emit(remaining)
                self._type_text(remaining)

        self._set_state(VoiceState.IDLE)

    def _on_partial(self, text: str):
        self.partial_text.emit(text)

    def _on_segment(self, text: str):
        """Called when Vosk confirms a complete sentence — paste immediately."""
        text = self._clean_text(text)
        if text:
            self.final_text.emit(text)
            self._type_text(text)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
        text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[，。！？、；：""''（）])', '', text)
        text = re.sub(r'(?<=[，。！？、；：""''（）])\s+(?=[\u4e00-\u9fff])', '', text)
        return text.strip()

    def _type_text(self, text: str):
        clipboard = QApplication.clipboard()
        old_text = clipboard.text()
        clipboard.setText(text)
        QTimer.singleShot(50, lambda: self._paste_and_restore(old_text))

    def _paste_and_restore(self, old_clipboard: str):
        self._simulate_ctrl_v()
        QTimer.singleShot(200, lambda: QApplication.clipboard().setText(old_clipboard))

    def _simulate_ctrl_v(self):
        if sys.platform != "linux":
            self.error.emit("当前平台不支持自动粘贴")
            return
        try:
            from Xlib import X, display as xdisplay, XK
            from Xlib.ext import xtest

            d = xdisplay.Display()
            ctrl_code = d.keysym_to_keycode(XK.string_to_keysym("Control_L"))
            v_code = d.keysym_to_keycode(XK.string_to_keysym("v"))

            xtest.fake_input(d, X.KeyPress, ctrl_code)
            xtest.fake_input(d, X.KeyPress, v_code)
            xtest.fake_input(d, X.KeyRelease, v_code)
            xtest.fake_input(d, X.KeyRelease, ctrl_code)
            d.sync()
        except Exception as e:
            print(f"[Voice] xlib paste failed: {e}, trying xdotool", flush=True)
            try:
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                    timeout=2, capture_output=True,
                )
            except Exception as e2:
                self.error.emit(f"粘贴失败: {e2}")

    def _set_state(self, state: str):
        self._state = state
        self.state_changed.emit(state)

    def cleanup(self):
        if self._rec_proc is not None:
            try:
                self._rec_proc.terminate()
                self._rec_proc.wait(timeout=2)
            except Exception:
                try:
                    self._rec_proc.kill()
                except Exception:
                    pass
            self._rec_proc = None
        self._set_state(VoiceState.IDLE)
