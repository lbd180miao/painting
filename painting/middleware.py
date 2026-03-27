from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpResponse
from django.template.loader import render_to_string


def has_pending_migrations() -> bool:
    connection = connections["default"]
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    return bool(executor.migration_plan(targets))


class PendingMigrationBlockerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if self._should_skip(path):
            return self.get_response(request)

        if has_pending_migrations():
            return HttpResponse(
                render_to_string("system/pending_migrations.html"),
                status=503,
            )

        return self.get_response(request)

    def _should_skip(self, path: str) -> bool:
        if settings.STATIC_URL and path.startswith(settings.STATIC_URL):
            return True
        if settings.MEDIA_URL and path.startswith(settings.MEDIA_URL):
            return True
        return False
