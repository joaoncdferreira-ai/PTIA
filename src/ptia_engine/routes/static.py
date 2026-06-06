from __future__ import annotations

from http import HTTPStatus
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import unquote, urlparse


def dashboard_do_get(handler) -> None:
    path = urlparse(handler.path).path
    if path == "/":
        handler._send_html()
        return
    if path == "/api/state":
        handler._send_json(handler.state.snapshot())
        return
    if path == "/api/health":
        from ptia_engine.cloud_state import CloudStateConfig

        handler._send_json(
            {
                "status": "ok",
                "cloud_state_enabled": CloudStateConfig.from_env() is not None,
            }
        )
        return
    if path == "/api/site-feed":
        from ptia_engine.dashboard import _site_feed

        handler._send_json(_site_feed(handler.state))
        return
    if path in {"/site", "/site/"}:
        handler._send_site_file("index.html")
        return
    if path == "/admin":
        handler._send_site_file("admin.html")
        return
    if path in {
        "/quem-e-quem",
        "/site/quem-e-quem",
        "/quem-e-quem.html",
        "/site/quem-e-quem.html",
    }:
        handler._send_site_file("quem-e-quem.html")
        return
    if path.startswith("/site/"):
        handler._send_site_file(path.removeprefix("/site/"))
        return
    if path == "/asset":
        query = urlparse(handler.path).query
        params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
        raw_path = params.get("path", "")

        asset_path = Path(unquote(raw_path)).resolve()
        data_root = handler.state.data_dir.resolve()
        if data_root not in asset_path.parents and asset_path != data_root:
            handler._send_json({"error": "invalid asset path"}, HTTPStatus.BAD_REQUEST)
            return
        if not asset_path.exists():
            handler._send_json({"error": "asset not found"}, HTTPStatus.NOT_FOUND)
            return
        data = asset_path.read_bytes()
        handler.send_response(HTTPStatus.OK)
        content_type = guess_type(str(asset_path))[0] or "application/octet-stream"
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return

    site_root = handler.state.site_dir.resolve()
    rel_path = path.lstrip("/")
    if rel_path:
        target = (site_root / rel_path).resolve()
        if site_root in target.parents or target == site_root:
            if target.exists() and target.is_file():
                handler._send_site_file(rel_path)
                return
    handler._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
