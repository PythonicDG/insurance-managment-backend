from .context import audit_context


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Keep the request itself: DRF authenticates later than Django middleware.
        with audit_context(request):
            return self.get_response(request)
