"""API router for request dispatch."""

from __future__ import annotations

from collections.abc import Callable

from apex_autopilot_optimization.api.request import APIRequest
from apex_autopilot_optimization.api.response import APIResponse

Handler = Callable[[APIRequest], APIResponse]


class APIRouter:
    """Routes API requests to registered handlers.

    Usage:
        router = APIRouter()
        router.get("/path", handler)
        response = router.dispatch(request)
    """

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Handler] = {}

    def route(self, path: str, method: str, handler: Handler) -> None:
        """Register a handler for a path and HTTP method."""
        self.routes[(method.upper(), path)] = handler

    def get(self, path: str, handler: Handler) -> None:
        """Register a GET handler."""
        self.route(path, "GET", handler)

    def post(self, path: str, handler: Handler) -> None:
        """Register a POST handler."""
        self.route(path, "POST", handler)

    def put(self, path: str, handler: Handler) -> None:
        """Register a PUT handler."""
        self.route(path, "PUT", handler)

    def delete(self, path: str, handler: Handler) -> None:
        """Register a DELETE handler."""
        self.route(path, "DELETE", handler)

    def dispatch(self, request: APIRequest) -> APIResponse:
        """Dispatch a request to the appropriate handler.

        Returns 404 if no handler is registered for the method+path.
        """
        key = (request.method.upper(), request.path)
        handler = self.routes.get(key)
        if handler is None:
            return APIResponse.not_found(f"No route for {request.method} {request.path}")
        return handler(request)


def api_route(router: APIRouter, path: str, method: str) -> Callable[[Handler], Handler]:
    """Decorator that registers a handler on a router.

    Usage:
        @api_route(router, "/ping", "GET")
        def ping(request):
            return APIResponse.success({"pong": True})
    """

    def decorator(func: Handler) -> Handler:
        router.route(path, method, func)
        return func

    return decorator
