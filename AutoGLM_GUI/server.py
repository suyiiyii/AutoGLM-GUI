"""AutoGLM-GUI Backend API Server (FastAPI + Socket.IO)."""

from socketio import ASGIApp

from AutoGLM_GUI.api import app as fastapi_app
from AutoGLM_GUI.socketio_server import sio

app = ASGIApp(
    other_asgi_app=fastapi_app, socketio_server=sio, socketio_path="/socket.io"
)

__all__ = ["app"]
