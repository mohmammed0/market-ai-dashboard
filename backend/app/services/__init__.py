from .cache import get_cache


def start_scheduler(*args, **kwargs):
    from .scheduler_runtime import start_scheduler as _start_scheduler

    return _start_scheduler(*args, **kwargs)


def stop_scheduler(*args, **kwargs):
    from .scheduler_runtime import stop_scheduler as _stop_scheduler

    return _stop_scheduler(*args, **kwargs)


def get_scheduler_status(*args, **kwargs):
    from .scheduler_runtime import get_scheduler_status as _get_scheduler_status

    return _get_scheduler_status(*args, **kwargs)


def can_current_process_run_scheduler(*args, **kwargs):
    from .scheduler_runtime import can_current_process_run_scheduler as _can_current_process_run_scheduler

    return _can_current_process_run_scheduler(*args, **kwargs)


__all__ = ["get_cache", "start_scheduler", "stop_scheduler", "get_scheduler_status", "can_current_process_run_scheduler"]
