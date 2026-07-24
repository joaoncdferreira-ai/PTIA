import json
import os
import shutil
import unittest
import urllib.error
import uuid

from pathlib import Path
from unittest.mock import patch

from ptia_engine.cloud_state import (
    CloudStateClient,
    CloudStateConfig,
    CloudStateConflictError,
    CloudStateMirror,
    reset_cloud_state_mirror,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        return None


class CloudStateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        reset_cloud_state_mirror()

    def tearDown(self):
        reset_cloud_state_mirror()
        shutil.rmtree(self.root, ignore_errors=True)

    def _config(self):
        return CloudStateConfig(
            api_url="https://state.example.test",
            token="secret",
            sync_ttl_seconds=0,
        )

    def test_config_requires_url_and_token(self):
        self.assertIsNone(CloudStateConfig.from_env({}))
        self.assertIsNone(CloudStateConfig.from_env({"PTIA_STATE_API_URL": "https://state"}))

        config = CloudStateConfig.from_env(
            {
                "PTIA_STATE_API_URL": "https://state/",
                "PTIA_STATE_TOKEN": "token",
                "PTIA_CLOUD_STATE_ENABLED": "true",
            }
        )

        self.assertIsNotNone(config)
        self.assertEqual(config.api_url, "https://state")

    def test_config_strips_utf8_bom_from_token(self):
        config = CloudStateConfig.from_env(
            {
                "PTIA_STATE_TOKEN": "\ufefftoken",
                "PTIA_CLOUD_STATE_ENABLED": "true",
            }
        )

        self.assertIsNotNone(config)
        self.assertEqual(config.token, "token")

    def test_client_sends_bearer_token_and_expected_version(self):
        seen = []

        def transport(request, *, timeout):
            seen.append(request)
            if request.method == "GET":
                return FakeResponse(
                    {
                        "dataset": "final_posts.jsonl",
                        "content": '{"id": 1}\n',
                        "sha256": "remote-sha",
                    }
                )
            return FakeResponse(
                {
                    "dataset": "final_posts.jsonl",
                    "sha256": "new-sha",
                }
            )

        client = CloudStateClient(self._config(), transport=transport)

        document = client.get("final_posts.jsonl")
        updated = client.put(
            "final_posts.jsonl",
            '{"id": 2}\n',
            expected_sha256="remote-sha",
        )

        self.assertEqual(document.content, '{"id": 1}\n')
        self.assertEqual(updated.sha256, "new-sha")
        self.assertEqual(seen[0].headers["Authorization"], "Bearer secret")
        body = json.loads(seen[1].data.decode("utf-8"))
        self.assertEqual(body["expected_sha256"], "remote-sha")

    def test_client_maps_http_409_to_conflict(self):
        def transport(request, *, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                409,
                "Conflict",
                {},
                fp=FakeResponse({"error": "Version conflict"}),
            )

        client = CloudStateClient(self._config(), transport=transport)

        with self.assertRaises(CloudStateConflictError):
            client.put("final_posts.jsonl", "content", expected_sha256="old")

    def test_mirror_hydrates_and_persists_managed_file(self):
        remote = {
            "content": '{"post_id":"remote"}\n',
            "sha": "remote-sha",
        }

        class FakeClient:
            config = CloudStateConfig("https://state", "token", 0)

            def get(self, dataset):
                from ptia_engine.cloud_state import CloudStateDocument

                return CloudStateDocument(dataset, remote["content"], remote["sha"])

            def put(self, dataset, content, *, expected_sha256):
                from ptia_engine.cloud_state import CloudStateDocument

                self.expected_sha = expected_sha256
                remote["content"] = content
                remote["sha"] = "updated-sha"
                return CloudStateDocument(dataset, content, remote["sha"])

        client = FakeClient()
        mirror = CloudStateMirror(client)
        path = self.root / "final_posts.jsonl"
        path.write_text('{"post_id":"local"}\n', encoding="utf-8")

        mirror.sync(path, force=True)
        self.assertIn("remote", path.read_text(encoding="utf-8"))
        path.write_text('{"post_id":"edited"}\n', encoding="utf-8")
        mirror.persist(path)

        self.assertIn("edited", remote["content"])
        self.assertEqual(client.expected_sha, "remote-sha")

    def test_mirror_preserves_local_content_on_version_conflict(self):
        remote_content = '{"post_id":"newer-remote"}\n'

        class ConflictingClient:
            config = CloudStateConfig("https://state", "token", 0)

            def get(self, dataset):
                from ptia_engine.cloud_state import CloudStateDocument

                return CloudStateDocument(dataset, remote_content, "remote-sha")

            def put(self, dataset, content, *, expected_sha256):
                raise CloudStateConflictError("Version conflict")

        mirror = CloudStateMirror(ConflictingClient())
        path = self.root / "final_posts.jsonl"
        path.write_text('{"post_id":"local-edit"}\n', encoding="utf-8")

        with self.assertRaises(CloudStateConflictError):
            mirror.persist(path)

        self.assertEqual(path.read_text(encoding="utf-8"), remote_content)
        backups = list((self.root / ".cloud_conflicts").glob("final_posts.jsonl.*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("local-edit", backups[0].read_text(encoding="utf-8"))

    def test_local_storage_does_not_require_cloud_configuration(self):
        from ptia_engine.models import NewsletterIssue
        from ptia_engine.storage import append_jsonl, load_newsletter_issues

        path = self.root / "newsletter_issues.jsonl"
        with patch.dict(os.environ, {}, clear=True):
            reset_cloud_state_mirror()
            append_jsonl(
                path,
                [
                    NewsletterIssue(
                        issue_id="weekly_local",
                        title="Local",
                        subject="Local",
                        preheader="",
                        intro="",
                        html="<html>{{ unsubscribe }}</html>",
                        text="Local",
                    )
                ],
            )

        self.assertEqual(load_newsletter_issues(path)[0].issue_id, "weekly_local")


if __name__ == "__main__":
    unittest.main()
