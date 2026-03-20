import sys
import os
import argparse

def _ensure_single_instance():
    import fcntl, signal
    lock_path = os.path.expanduser("~/.fastpanel.lock")
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        try:
            with open(lock_path, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"FastPanel is already running (PID {old_pid}).")
        except (ValueError, ProcessLookupError, PermissionError):
            os.remove(lock_path)
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_fd.write(str(os.getpid()))
            lock_fd.flush()
            return lock_fd
        sys.exit(0)
    lock_fd.write(str(os.getpid()))
    lock_fd.flush()
    return lock_fd

def main():
    parser = argparse.ArgumentParser(description="FastPanel")
    parser.add_argument("--desktop", action="store_true", help="Run as desktop widget")
    args = parser.parse_args()

    if args.desktop:
        import fastpanel.constants as _const
        _const._DESKTOP_MODE = True

    lock = _ensure_single_instance()

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)

    from fastpanel.windows.main_window import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
