import unittest
from unittest.mock import patch

from ptia_engine.buffer_api import BufferClient


class BufferClientTests(unittest.TestCase):
    def test_parses_account_organizations(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "account": {
                        "organizations": [{"id": "org_1", "name": "PTIA"}],
                    }
                }
            },
        ):
            organizations = client.account_organizations()

        self.assertEqual(organizations[0].id, "org_1")
        self.assertEqual(organizations[0].name, "PTIA")

    def test_parses_channels(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "channels": [
                        {
                            "id": "chan_1",
                            "name": "ptia.pt",
                            "displayName": "PTIA",
                            "service": "instagram",
                        }
                    ]
                }
            },
        ):
            channels = client.channels("org_1")

        self.assertEqual(channels[0].id, "chan_1")
        self.assertEqual(channels[0].service, "instagram")

    def test_parses_created_post(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "createPost": {
                        "post": {
                            "id": "post_1",
                            "text": "Hello",
                            "dueAt": "2026-05-15T09:00:00+01:00",
                        }
                    }
                }
            },
        ) as graphql:
            post = client.create_scheduled_post(
                channel_id="chan_1",
                text="Hello",
                due_at="2026-05-15T09:00:00+01:00",
                image_url="https://ptia.pt/assets/image.jpg",
                post_type="post",
            )

        self.assertEqual(post.id, "post_1")
        variables = graphql.call_args.args[1]
        self.assertEqual(
            variables["input"]["assets"][0]["image"]["url"],
            "https://ptia.pt/assets/image.jpg",
        )
        self.assertEqual(variables["input"]["metadata"]["instagram"]["type"], "post")
        self.assertIs(variables["input"]["metadata"]["instagram"]["shouldShareToFeed"], True)

    def test_parses_edited_post_with_asset(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "editPost": {
                        "post": {
                            "id": "post_1",
                            "text": "Hello updated",
                            "dueAt": "2026-05-15T09:00:00+01:00",
                        }
                    }
                }
            },
        ) as graphql:
            post = client.edit_scheduled_post(
                post_id="post_1",
                text="Hello updated",
                due_at="2026-05-15T09:00:00+01:00",
                image_url="https://ptia.pt/assets/image.jpg",
            )

        self.assertEqual(post.id, "post_1")
        variables = graphql.call_args.args[1]
        self.assertEqual(variables["input"]["id"], "post_1")
        self.assertEqual(
            variables["input"]["assets"][0]["image"]["url"],
            "https://ptia.pt/assets/image.jpg",
        )


if __name__ == "__main__":
    unittest.main()
