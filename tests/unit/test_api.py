"""Tests for the API layer."""

from __future__ import annotations

import pytest

from apex_autopilot_optimization.api import (
    APIError,
    APIKeyAuth,
    APIRequest,
    APIResponse,
    APIRouter,
    APIVersion,
    api_route,
    get_version,
    require_auth,
    version_route,
)

# ---------------------------------------------------------------------------
# Router — route registration
# ---------------------------------------------------------------------------


class TestRouterRegistration:
    """Tests for route registration on APIRouter."""

    def test_route_registers_handler(self) -> None:
        router = APIRouter()

        def handler(request: APIRequest) -> APIResponse:
            return APIResponse.success({"ok": True})

        router.route("/things", "GET", handler)
        assert ("GET", "/things") in router.routes

    def test_get_registers_get_method(self) -> None:
        router = APIRouter()

        def handler(request: APIRequest) -> APIResponse:
            return APIResponse.success({})

        router.get("/items", handler)
        assert ("GET", "/items") in router.routes

    def test_post_registers_post_method(self) -> None:
        router = APIRouter()

        def handler(request: APIRequest) -> APIResponse:
            return APIResponse.success({})

        router.post("/items", handler)
        assert ("POST", "/items") in router.routes

    def test_put_registers_put_method(self) -> None:
        router = APIRouter()

        def handler(request: APIRequest) -> APIResponse:
            return APIResponse.success({})

        router.put("/items/1", handler)
        assert ("PUT", "/items/1") in router.routes

    def test_delete_registers_delete_method(self) -> None:
        router = APIRouter()

        def handler(request: APIRequest) -> APIResponse:
            return APIResponse.success({})

        router.delete("/items/1", handler)
        assert ("DELETE", "/items/1") in router.routes

    def test_multiple_routes_coexist(self) -> None:
        router = APIRouter()

        def h(req: APIRequest) -> APIResponse:
            return APIResponse.success({})

        router.get("/a", h)
        router.post("/b", h)
        router.put("/c", h)
        router.delete("/d", h)
        assert len(router.routes) == 4


# ---------------------------------------------------------------------------
# Router — dispatch
# ---------------------------------------------------------------------------


class TestRouterDispatch:
    """Tests for dispatching requests through the router."""

    def test_dispatch_get(self) -> None:
        router = APIRouter()
        router.get("/hello", lambda req: APIResponse.success({"msg": "hi"}))
        req = APIRequest(method="GET", path="/hello", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"msg": "hi"}

    def test_dispatch_post(self) -> None:
        router = APIRouter()
        router.post("/echo", lambda req: APIResponse.success(req.body))
        req = APIRequest(method="POST", path="/echo", headers={}, body={"x": 1}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"x": 1}

    def test_dispatch_put(self) -> None:
        router = APIRouter()
        router.put("/update", lambda req: APIResponse.success({"updated": True}))
        req = APIRequest(method="PUT", path="/update", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"updated": True}

    def test_dispatch_delete(self) -> None:
        router = APIRouter()
        router.delete("/remove", lambda req: APIResponse.success({"deleted": True}))
        req = APIRequest(method="DELETE", path="/remove", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"deleted": True}

    def test_dispatch_unknown_route_returns_404(self) -> None:
        router = APIRouter()
        req = APIRequest(method="GET", path="/missing", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 404

    def test_dispatch_wrong_method_returns_404(self) -> None:
        router = APIRouter()
        router.get("/only-get", lambda req: APIResponse.success({}))
        req = APIRequest(method="POST", path="/only-get", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 404

    def test_dispatch_handler_receives_request(self) -> None:
        captured: list[APIRequest] = []

        def handler(req: APIRequest) -> APIResponse:
            captured.append(req)
            return APIResponse.success({})

        router = APIRouter()
        router.get("/capture", handler)
        req = APIRequest(
            method="GET", path="/capture", headers={"X-Test": "1"}, body={}, query_params={}
        )
        router.dispatch(req)
        assert len(captured) == 1
        assert captured[0].headers["X-Test"] == "1"


# ---------------------------------------------------------------------------
# APIRequest
# ---------------------------------------------------------------------------


class TestAPIRequest:
    """Tests for APIRequest dataclass."""

    def test_create_minimal_request(self) -> None:
        req = APIRequest(method="GET", path="/x", headers={}, body={}, query_params={})
        assert req.method == "GET"
        assert req.path == "/x"
        assert req.user is None

    def test_create_request_with_user(self) -> None:
        req = APIRequest(
            method="POST",
            path="/x",
            headers={"Authorization": "Bearer t"},
            body={"k": "v"},
            query_params={"q": "1"},
            user="alice",
        )
        assert req.user == "alice"
        assert req.body == {"k": "v"}
        assert req.query_params == {"q": "1"}


# ---------------------------------------------------------------------------
# APIResponse
# ---------------------------------------------------------------------------


class TestAPIResponse:
    """Tests for APIResponse factory methods."""

    def test_success_default_status(self) -> None:
        resp = APIResponse.success({"data": 42})
        assert resp.status == 200
        assert resp.body == {"data": 42}

    def test_success_custom_status(self) -> None:
        resp = APIResponse.success({"id": 1}, status=201)
        assert resp.status == 201

    def test_error_default_status(self) -> None:
        resp = APIResponse.error("bad input")
        assert resp.status == 400
        assert "bad input" in resp.body["error"]

    def test_error_custom_status(self) -> None:
        resp = APIResponse.error("server broke", status=500)
        assert resp.status == 500

    def test_not_found(self) -> None:
        resp = APIResponse.not_found("resource missing")
        assert resp.status == 404
        assert "resource missing" in resp.body["error"]

    def test_unauthorized(self) -> None:
        resp = APIResponse.unauthorized("no token")
        assert resp.status == 401
        assert "no token" in resp.body["error"]

    def test_headers_default_empty(self) -> None:
        resp = APIResponse.success({})
        assert resp.headers == {}


# ---------------------------------------------------------------------------
# APIError
# ---------------------------------------------------------------------------


class TestAPIError:
    """Tests for APIError exception."""

    def test_raise_and_catch(self) -> None:
        with pytest.raises(APIError) as exc_info:
            raise APIError("something failed", status_code=422)
        assert exc_info.value.status_code == 422
        assert "something failed" in str(exc_info.value)

    def test_default_status_code(self) -> None:
        err = APIError("oops")
        assert err.status_code == 400

    def test_details_field(self) -> None:
        err = APIError("validation", details={"field": "name"})
        assert err.details == {"field": "name"}

    def test_details_default_none(self) -> None:
        err = APIError("oops")
        assert err.details is None


# ---------------------------------------------------------------------------
# Auth — require_auth decorator
# ---------------------------------------------------------------------------


class TestRequireAuth:
    """Tests for the require_auth decorator."""

    def test_allows_authenticated_user(self) -> None:
        @require_auth
        def protected(req: APIRequest) -> APIResponse:
            return APIResponse.success({"secret": True})

        req = APIRequest(
            method="GET", path="/protected", headers={}, body={}, query_params={}, user="bob"
        )
        resp = protected(req)
        assert resp.status == 200
        assert resp.body == {"secret": True}

    def test_rejects_unauthenticated_user(self) -> None:
        @require_auth
        def protected(req: APIRequest) -> APIResponse:
            return APIResponse.success({"secret": True})

        req = APIRequest(method="GET", path="/protected", headers={}, body={}, query_params={})
        resp = protected(req)
        assert resp.status == 401

    def test_preserves_function_name(self) -> None:
        @require_auth
        def my_handler(req: APIRequest) -> APIResponse:
            return APIResponse.success({})

        assert my_handler.__name__ == "my_handler"


# ---------------------------------------------------------------------------
# Auth — APIKeyAuth
# ---------------------------------------------------------------------------


class TestAPIKeyAuth:
    """Tests for APIKeyAuth key management."""

    def test_generate_key_returns_string(self) -> None:
        auth = APIKeyAuth()
        key = auth.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0

    def test_validate_key_after_generation(self) -> None:
        auth = APIKeyAuth()
        key = auth.generate_key()
        assert auth.validate_key(key) is True

    def test_validate_unknown_key(self) -> None:
        auth = APIKeyAuth()
        assert auth.validate_key("nonexistent-key-xyz") is False

    def test_revoke_key(self) -> None:
        auth = APIKeyAuth()
        key = auth.generate_key()
        assert auth.validate_key(key) is True
        auth.revoke_key(key)
        assert auth.validate_key(key) is False

    def test_revoke_unknown_key_no_error(self) -> None:
        auth = APIKeyAuth()
        auth.revoke_key("never-existed")  # should not raise

    def test_multiple_keys_independent(self) -> None:
        auth = APIKeyAuth()
        k1 = auth.generate_key()
        k2 = auth.generate_key()
        auth.revoke_key(k1)
        assert auth.validate_key(k1) is False
        assert auth.validate_key(k2) is True


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


class TestVersioning:
    """Tests for API version routing and extraction."""

    def test_version_route_v1(self) -> None:
        router = APIRouter()

        @version_route(APIVersion.V1, "/status")
        def handler(req: APIRequest) -> APIResponse:
            return APIResponse.success({"version": "v1"})

        router.get("/v1/status", handler)
        req = APIRequest(method="GET", path="/v1/status", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"version": "v1"}

    def test_version_route_v2(self) -> None:
        router = APIRouter()

        @version_route(APIVersion.V2, "/status")
        def handler(req: APIRequest) -> APIResponse:
            return APIResponse.success({"version": "v2"})

        router.get("/v2/status", handler)
        req = APIRequest(method="GET", path="/v2/status", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"version": "v2"}

    def test_get_version_v1_path(self) -> None:
        assert get_version("/v1/resource") == APIVersion.V1

    def test_get_version_v2_path(self) -> None:
        assert get_version("/v2/resource") == APIVersion.V2

    def test_get_version_no_version(self) -> None:
        assert get_version("/resource") is None

    def test_get_version_nested_path(self) -> None:
        assert get_version("/api/v1/resource") == APIVersion.V1

    def test_api_route_decorator(self) -> None:
        router = APIRouter()

        @api_route(router, "/ping", "GET")
        def handler(req: APIRequest) -> APIResponse:
            return APIResponse.success({"pong": True})

        assert ("GET", "/ping") in router.routes
        req = APIRequest(method="GET", path="/ping", headers={}, body={}, query_params={})
        resp = router.dispatch(req)
        assert resp.status == 200
        assert resp.body == {"pong": True}
