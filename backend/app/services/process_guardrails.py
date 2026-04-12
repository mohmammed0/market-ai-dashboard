from __future__ import annotations

import os


def is_process_running(pid: int | None) -> bool:
    if pid in (None, "", 0):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except SystemError:
        return False
    except OSError:
        return False
