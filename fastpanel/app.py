import sys
import os
import signal
import socket
import argparse

_SOCK_PATH = os.path.expanduser("~/.fastpanel.sock")
_LOCK_PATH = os.path.expanduser("~/.fastpanel.lock")


def _notify_startup_complete():
    """Notify the desktop environment that startup is complete to stop the loading cursor."""
    startup_id = os.environ.get("DESKTOP_STARTUP_ID", "")
    if startup_id:
        try:
            import subprocess
            subprocess.Popen(
                ["xdotool", "set_desktop_viewport", "0", "0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    try:
        import gi
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gdk
        Gdk.notify_startup_complete()
    except Exception:
        pass
    os.environ.pop("DESKTOP_STARTUP_ID", None)


def _try_activate_existing():
    """Try to tell an existing FastPanel instance to raise its window.
    Returns True if the message was sent successfully (caller should exit)."""
    old_pid = None
    try:
        with open(_LOCK_PATH, "r") as f:
            old_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return False

    if old_pid and old_pid != os.getpid():
        try:
            os.kill(old_pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(_SOCK_PATH)
            sock.sendall(b"raise")
            sock.close()
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            try:
                os.kill(old_pid, signal.SIGUSR1)
                return True
            except (ProcessLookupError, PermissionError):
                return False
    return False


def _ensure_single_instance():
    import fcntl

    lock_fd = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("FastPanel: another instance is running, activating it.")
        sys.exit(0)

    lock_fd.write(str(os.getpid()))
    lock_fd.flush()
    return lock_fd


def _start_ipc_server(window):
    """Start a Unix domain socket server that listens for 'raise' commands."""
    from PyQt5.QtCore import QSocketNotifier

    try:
        os.unlink(_SOCK_PATH)
    except FileNotFoundError:
        pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.setblocking(False)
    srv.bind(_SOCK_PATH)
    srv.listen(1)

    def _on_connection():
        try:
            conn, _ = srv.accept()
            data = conn.recv(64)
            conn.close()
            if data == b"raise":
                window.show()
                window.raise_()
                window.activateWindow()
        except Exception:
            pass

    notifier = QSocketNotifier(srv.fileno(), QSocketNotifier.Read)
    notifier.activated.connect(_on_connection)

    window._ipc_srv = srv
    window._ipc_notifier = notifier


def main():
    try:
        from setproctitle import setproctitle
        setproctitle("fastpanel")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="FastPanel")
    parser.add_argument("--desktop", action="store_true", help="Run as desktop widget")
    args = parser.parse_args()

    if args.desktop:
        import fastpanel.constants as _const
        _const._DESKTOP_MODE = True

    if _try_activate_existing():
        print("FastPanel: existing instance activated.")
        _notify_startup_complete()
        sys.exit(0)

    lock = _ensure_single_instance()

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)

    from fastpanel.windows.main_window import MainWindow
    w = MainWindow()
    w.show()

    _start_ipc_server(w)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
