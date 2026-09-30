from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from uuid import uuid4


current_request = ContextVar("audit_request", default=None)
operation_id = ContextVar("audit_operation_id", default=None)


def audit_operation(function):
    """Give cascades and jobs one correlation ID, without changing request identity."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if operation_id.get() is not None:
            return function(*args, **kwargs)
        token = operation_id.set(uuid4())
        try:
            return function(*args, **kwargs)
        finally:
            operation_id.reset(token)
    return wrapped


@contextmanager
def audit_context(request=None):
    """Isolated request context; also usable by jobs and management commands."""
    request_token = current_request.set(request)
    id_token = operation_id.set(uuid4())
    try:
        yield
    finally:
        operation_id.reset(id_token)
        current_request.reset(request_token)
