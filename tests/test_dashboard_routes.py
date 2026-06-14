import shutil
import unittest
import uuid
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ptia_engine.dashboard import DashboardHandler, DashboardState
from ptia_engine.routes import POST_ROUTES, dashboard_do_get


class DashboardRoutesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_dashboard_handler_delegates_http_methods_to_routes_module(self):
        handler = SimpleNamespace()

        with patch("ptia_engine.routes.dashboard_do_get") as get_route:
            DashboardHandler.do_GET(handler)
        with patch("ptia_engine.routes.dashboard_do_post") as post_route:
            DashboardHandler.do_POST(handler)

        get_route.assert_called_once_with(handler)
        post_route.assert_called_once_with(handler)

    def test_state_get_route_returns_dashboard_snapshot(self):
        calls = []
        handler = SimpleNamespace(
            path="/api/state",
            state=DashboardState(self.root),
            _send_json=lambda payload, status=HTTPStatus.OK: calls.append((payload, status)),
        )

        dashboard_do_get(handler)

        self.assertEqual(calls[0][1], HTTPStatus.OK)
        self.assertIn("counts", calls[0][0])
        self.assertIn("final_posts", calls[0][0])

    def test_post_routes_are_registered_by_domain_modules(self):
        expected = {
            "/api/item-status": "ptia_engine.routes.editorial",
            "/api/draft-status": "ptia_engine.routes.editorial",
            "/api/performance": "ptia_engine.routes.editorial",
            "/api/newsletter-generate": "ptia_engine.routes.newsletter",
            "/api/newsletter-status": "ptia_engine.routes.newsletter",
            "/api/build-final-pack": "ptia_engine.routes.posts",
            "/api/reverify-signal": "ptia_engine.routes.signals",
            "/api/schedule-package": "ptia_engine.routes.scheduling",
            "/api/editorial-automation": "ptia_engine.routes.automation",
            "/api/replace-editorial-package": "ptia_engine.routes.automation",
        }

        for path, module_name in expected.items():
            self.assertIn(path, POST_ROUTES)
            self.assertEqual(POST_ROUTES[path].__module__, module_name)


if __name__ == "__main__":
    unittest.main()
