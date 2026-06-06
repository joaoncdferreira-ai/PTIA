import hashlib
import importlib.util
import os
import shutil
import sys
import unittest
import uuid

from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CloudProductionScriptTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_jsonl_summary_validates_and_hashes_content(self):
        module = load_script_module(
            "newsletter_preflight_test",
            "newsletter_production_preflight.py",
        )
        path = self.root / "state.jsonl"
        content = '{"id":1}\n{"id":2}\n'
        path.write_text(content, encoding="utf-8")

        count, digest = module._jsonl_summary(path)

        self.assertEqual(count, 2)
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_render_configuration_updates_only_required_variables(self):
        module = load_script_module("render_config_test", "configure_render_cloud_state.py")
        calls = []

        def fake_request(path, *, api_key, method="GET", payload=None):
            calls.append((path, api_key, method, payload))
            return {}

        with patch.object(module, "_render_request", side_effect=fake_request):
            module.configure_render(
                api_key="render-key",
                service_id="srv-123",
                state_token="state-secret",
                state_api_url="https://state.example",
                enable=True,
            )

        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call[2] == "PUT" for call in calls))
        values = {call[0].split("/")[-1]: call[3]["value"] for call in calls}
        self.assertEqual(values["PTIA_CLOUD_STATE_ENABLED"], "true")
        self.assertEqual(values["PTIA_STATE_TOKEN"], "state-secret")

    def test_render_service_id_is_discovered_by_name(self):
        module = load_script_module("render_discovery_test", "configure_render_cloud_state.py")

        with patch.object(
            module,
            "_render_request",
            return_value=[
                {
                    "service": {
                        "id": "srv-123",
                        "name": "ptia-dashboard",
                        "slug": "ptia-dashboard",
                    }
                }
            ],
        ):
            service_id = module.discover_service_id(
                api_key="render-key",
                service_name="ptia-dashboard",
            )

        self.assertEqual(service_id, "srv-123")

    def test_preflight_detects_missing_secrets_without_exposing_values(self):
        module = load_script_module(
            "newsletter_preflight_secrets_test",
            "newsletter_production_preflight.py",
        )
        with patch.dict(os.environ, {}, clear=True):
            checks = module.local_checks(self.root)

        secret_checks = [check for check in checks if check.name.startswith("secret:")]
        self.assertTrue(secret_checks)
        self.assertTrue(all(not check.passed for check in secret_checks))
        self.assertTrue(all(check.detail == "missing" for check in secret_checks))


if __name__ == "__main__":
    unittest.main()
