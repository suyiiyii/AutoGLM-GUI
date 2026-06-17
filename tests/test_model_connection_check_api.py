"""Contract tests for model connection check endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from AutoGLM_GUI.api.agents import router as agents_router

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]

URL = "/api/config/model-connection-check"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int = 200,
    json_data: Any = None,
    text: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(agents_router)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_base_url(self) -> None:
        client = TestClient(_build_app())
        resp = client.post(URL, json={"base_url": "", "model_name": "m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "Base URL" in body["message"]

    def test_missing_model_name(self) -> None:
        client = TestClient(_build_app())
        resp = client.post(
            URL, json={"base_url": "http://localhost:8080/v1", "model_name": ""}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "模型名称" in body["message"]


class TestConnectionSuccess:
    def test_model_found_local(self) -> None:
        mock_resp = _make_response(200, {"data": [{"id": "m1"}, {"id": "m2"}]})
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m1"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]
        assert "本地" in body["message"]

    def test_model_found_remote(self) -> None:
        mock_resp = _make_response(200, {"data": [{"id": "gpt-4o"}]})
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL,
                json={"base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"},
            )

        body = resp.json()
        assert body["success"] is True
        assert "在线" in body["message"]

    def test_api_key_sent_in_header(self) -> None:
        mock_resp = _make_response(200, {"data": [{"id": "m1"}]})
        mock_get = MagicMock(return_value=mock_resp)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.get = mock_get
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            client.post(
                URL,
                json={
                    "base_url": "http://localhost:8080/v1",
                    "model_name": "m1",
                    "api_key": "sk-test",
                },
            )

        call_headers = mock_get.call_args[1].get(
            "headers"
        ) or mock_get.call_args.kwargs.get("headers", {})
        assert call_headers.get("Authorization") == "Bearer sk-test"

    def test_trailing_slash_stripped(self) -> None:
        mock_resp = _make_response(200, {"data": [{"id": "m1"}]})
        mock_get = MagicMock(return_value=mock_resp)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.get = mock_get
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            client.post(
                URL, json={"base_url": "http://localhost:8080/v1/", "model_name": "m1"}
            )

        called_url = mock_get.call_args[0][0]
        assert called_url == "http://localhost:8080/v1/models"


class TestModelNotFound:
    def test_model_not_in_list(self) -> None:
        mock_resp = _make_response(
            200, {"data": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        )
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL,
                json={"base_url": "http://localhost:8080/v1", "model_name": "missing"},
            )

        body = resp.json()
        assert body["success"] is False
        assert "未找到模型" in body["message"]
        assert "a, b, c" in body["message"]

    def test_empty_model_list(self) -> None:
        mock_resp = _make_response(200, {"data": []})
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "未返回模型列表" in body["message"]

    def test_no_data_key(self) -> None:
        mock_resp_models = _make_response(200, {})
        mock_resp_chat = _make_response(500, text="Chat error")
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(return_value=mock_resp_models)
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "Chat error" in body["message"]


class TestHTTPError:
    def test_non_200_status(self) -> None:
        mock_resp_models = _make_response(401, text="Unauthorized")
        mock_resp_chat = _make_response(401, text="Unauthorized")
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "请求失败" in body["message"]
        assert "401" in body["message"]

    def test_404_fallback_to_chat_completions(self) -> None:
        mock_resp_models = _make_response(404, text="Not Found")
        mock_resp_chat = _make_response(200)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            mock_ctx.get = get_mock
            mock_ctx.post = MagicMock(return_value=mock_resp_chat)
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]

    def test_500_fallback_to_chat_completions(self) -> None:
        mock_resp_models = _make_response(500, text="Internal Server Error")
        mock_resp_chat = _make_response(200)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            mock_ctx.get = get_mock
            mock_ctx.post = MagicMock(return_value=mock_resp_chat)
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]

    def test_403_fallback_allowed(self) -> None:
        mock_resp_models = _make_response(403, text="Forbidden")
        mock_resp_chat = _make_response(200)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]

    def test_401_fallback_allowed(self) -> None:
        mock_resp_models = _make_response(401, text="Unauthorized")
        mock_resp_chat = _make_response(200)
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]

    def test_auth_fallback_auth_failure(self) -> None:
        mock_resp_models = _make_response(403, text="Forbidden")
        mock_resp_chat = _make_response(401, text="Unauthorized")
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "请求失败" in body["message"]
        assert "401" in body["message"]

    def test_json_parsing_error_fallback(self) -> None:
        mock_resp_models = MagicMock()
        mock_resp_models.status_code = 200
        mock_resp_models.json.side_effect = ValueError("Invalid JSON")
        mock_resp_models.text = "<html>Error page</html>"

        mock_resp_chat = _make_response(200)

        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            get_mock = MagicMock(side_effect=[mock_resp_models, mock_resp_chat])
            post_mock = MagicMock(return_value=mock_resp_chat)
            mock_ctx.get = get_mock
            mock_ctx.post = post_mock
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is True
        assert "连接成功" in body["message"]


class TestNetworkError:
    def test_connection_error(self) -> None:
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.get.side_effect = httpx.ConnectError("refused")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "无法连接" in body["message"]

    def test_timeout(self) -> None:
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.get.side_effect = httpx.TimeoutException("timed out")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "超时" in body["message"]

    def test_unexpected_error(self) -> None:
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.get.side_effect = RuntimeError("boom")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL, json={"base_url": "http://localhost:8080/v1", "model_name": "m"}
            )

        body = resp.json()
        assert body["success"] is False
        assert "boom" in body["message"]


class TestModelListTruncation:
    def test_many_models_truncated(self) -> None:
        models = [{"id": f"model-{i}"} for i in range(15)]
        mock_resp = _make_response(200, {"data": models})
        with patch("AutoGLM_GUI.api.agents.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(
                return_value=MagicMock(get=MagicMock(return_value=mock_resp))
            )
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client = TestClient(_build_app())
            resp = client.post(
                URL,
                json={"base_url": "http://localhost:8080/v1", "model_name": "missing"},
            )

        body = resp.json()
        assert body["success"] is False
        assert "...(+5)" in body["message"]
