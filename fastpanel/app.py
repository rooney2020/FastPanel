import sys
import os
import argparse

def _ensure_single_instance():
    import fcntl, signal, time
    lock_path = os.path.expanduser("~/.fastpanel.lock")

    old_pid = None
    try:
        with open(lock_path, "r") as f:
            old_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    if old_pid and old_pid != os.getpid():
        try:
            os.kill(old_pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.1)
                try:
                    os.kill(old_pid, 0)
                except ProcessLookupError:
                    break
            else:
                try:
                    os.kill(old_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except (ProcessLookupError, PermissionError):
            pass

    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("FastPanel: failed to acquire lock, another instance may be running.")
        sys.exit(1)

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
