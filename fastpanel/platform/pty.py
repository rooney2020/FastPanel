import os
import re
import subprocess
import pty
import select
import errno
import fcntl
import signal
import html as _html_mod

from PyQt5.QtCore import QThread, pyqtSignal

_CSI_RE_B = re.compile(rb'\x1b\[([0-9;?]*)([A-Za-z@`])')
_NON_CSI_B = re.compile(
    rb'\x1b(?:'
    rb'\][^\x07\x1b]*(?:\x07|\x1b\\)'   # OSC
    rb'|[()][A-Z0-9]'                   # charset
    rb'|[>=<]'                           # keypad/cursor
    rb'|[^[\]])'                         # other single-char
    rb'|\x07|\r'
)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_SGR_RE = re.compile(r'\x1b\[([0-9;]*)m')

def _filter_csi(m):
    return m.group(0) if m.group(2) == b'm' else b""

def _clean_pty(raw: bytes, keep_color=False) -> str:
    if keep_color:
        clean = _CSI_RE_B.sub(_filter_csi, raw)
    else:
        clean = _CSI_RE_B.sub(b"", raw)
    clean = _NON_CSI_B.sub(b"", clean)
    text = clean.decode("utf-8", errors="replace")
    return _CTRL_RE.sub("", text)

_TC16 = {
    0: '#45475a', 1: '#f38ba8', 2: '#a6e3a1', 3: '#f9e2af',
    4: '#89b4fa', 5: '#cba6f7', 6: '#94e2d5', 7: '#bac2de',
    8: '#585b70', 9: '#f38ba8', 10: '#a6e3a1', 11: '#f9e2af',
    12: '#89b4fa', 13: '#cba6f7', 14: '#94e2d5', 15: '#a6adc8',
}

def _c256(n):
    if n < 16: return _TC16.get(n, '')
    if n < 232:
        n -= 16; return f'#{(n//36)*51:02x}{((n%36)//6)*51:02x}{(n%6)*51:02x}'
    v = 8 + (n - 232) * 10; return f'#{v:02x}{v:02x}{v:02x}'

def _ansi_to_html(text: str) -> str:
    parts = []; spans = 0; pos = 0
    for m in _SGR_RE.finditer(text):
        parts.append(_html_mod.escape(text[pos:m.start()]))
        pos = m.end()
        codes = [int(c) for c in m.group(1).split(';') if c] if m.group(1) else [0]
        styles = []; i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                parts.append('</span>' * spans); spans = 0
            elif c == 1: styles.append('font-weight:bold')
            elif c == 3: styles.append('font-style:italic')
            elif c == 4: styles.append('text-decoration:underline')
            elif 30 <= c <= 37:
                cl = _TC16.get(c - 30, ''); cl and styles.append(f'color:{cl}')
            elif 40 <= c <= 47:
                cl = _TC16.get(c - 40, ''); cl and styles.append(f'background-color:{cl}')
            elif 90 <= c <= 97:
                cl = _TC16.get(c - 90 + 8, ''); cl and styles.append(f'color:{cl}')
            elif c == 38 and i + 2 < len(codes) and codes[i+1] == 5:
                cl = _c256(codes[i+2]); cl and styles.append(f'color:{cl}'); i += 2
            elif c == 48 and i + 2 < len(codes) and codes[i+1] == 5:
                cl = _c256(codes[i+2]); cl and styles.append(f'background-color:{cl}'); i += 2
            elif c == 38 and i + 4 < len(codes) and codes[i+1] == 2:
                styles.append(f'color:#{codes[i+2]:02x}{codes[i+3]:02x}{codes[i+4]:02x}'); i += 4
            elif c == 48 and i + 4 < len(codes) and codes[i+1] == 2:
                styles.append(f'background-color:#{codes[i+2]:02x}{codes[i+3]:02x}{codes[i+4]:02x}'); i += 4
            i += 1
        if styles:
            parts.append(f'<span style="{";".join(styles)}">'); spans += 1
    parts.append(_html_mod.escape(text[pos:]))
    parts.append('</span>' * spans)
    return ''.join(parts)


class PtyRunner(QThread):
    line_ready = pyqtSignal(str)
    done = pyqtSignal(int)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._master_fd = -1
        self._proc = None
        self._stopped = False

    def write_stdin(self, text):
        if self._master_fd >= 0:
            try:
                os.write(self._master_fd, (text + "\n").encode())
            except OSError:
                pass

    def stop(self):
        self._stopped = True
        if self._proc and self._proc.poll() is None:
            try:
                pgid = os.getpgid(self._proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                try:
                    self._proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    self._proc.kill()
                except OSError:
                    pass

    def run(self):
        master_fd = -1
        try:
            master_fd, slave_fd = pty.openpty()
            self._master_fd = master_fd
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            env = os.environ.copy()
            env.setdefault("TERM", "xterm-256color")
            self._proc = subprocess.Popen(
                self.cmd, shell=True,
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                preexec_fn=os.setsid, close_fds=True, env=env
            )
            os.close(slave_fd)

            buf = b""
            idle = 0
            while not self._stopped:
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.05)
                except (ValueError, OSError):
                    break
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError as ex:
                        if ex.errno == errno.EIO:
                            break
                        if ex.errno == errno.EAGAIN:
                            continue
                        break
                    if not chunk:
                        break
                    buf += chunk
                    idle = 0
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.line_ready.emit(_clean_pty(line, keep_color=True))
                else:
                    idle += 1
                    if buf and idle >= 2:
                        self.line_ready.emit(_clean_pty(buf, keep_color=True))
                        buf = b""
                        idle = 0
                if self._proc.poll() is not None:
                    try:
                        while True:
                            rest = os.read(master_fd, 4096)
                            if not rest:
                                break
                            buf += rest
                    except OSError:
                        pass
                    break
            if buf:
                self.line_ready.emit(_clean_pty(buf, keep_color=True))
            code = self._proc.wait() if self._proc else -1
            if self._stopped:
                code = -15
        except Exception as e:
            self.line_ready.emit(f"错误: {e}")
            code = -1
        finally:
            if master_fd >= 0:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
                self._master_fd = -1
        self.done.emit(code)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

