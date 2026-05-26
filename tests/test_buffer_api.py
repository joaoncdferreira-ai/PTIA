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
        self.assertEqual(variables["input"]["dueAt"], "2026-05-15T08:00:00.000Z")

    def test_create_post_supports_multiple_image_assets(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "createPost": {
                        "post": {
                            "id": "post_1",
                            "text": "Carousel",
                            "dueAt": "2026-05-15T09:00:00+01:00",
                        }
                    }
                }
            },
        ) as graphql:
            post = client.create_scheduled_post(
                channel_id="chan_1",
                text="Carousel",
                due_at="2026-05-15T09:00:00+01:00",
                image_urls=[
                    "https://ptia.pt/assets/one.jpg",
                    "https://ptia.pt/assets/two.jpg",
                ],
                post_type="post",
            )

        self.assertEqual(post.id, "post_1")
        variables = graphql.call_args.args[1]
        self.assertEqual(
            [asset["image"]["url"] for asset in variables["input"]["assets"]],
            [
                "https://ptia.pt/assets/one.jpg",
                "https://ptia.pt/assets/two.jpg",
            ],
        )

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
        self.assertEqual(variables["input"]["dueAt"], "2026-05-15T08:00:00.000Z")

    def test_get_post_reads_real_buffer_state(self):
        client = BufferClient(api_key="test")
        with patch.object(
            client,
            "_graphql",
            return_value={
                "data": {
                    "post": {
                        "id": "post_1",
                        "status": "scheduled",
                        "dueAt": "2026-05-15T08:00:00.000Z",
                        "text": "Real Buffer text",
                        "channelId": "chan_1",
                        "channelService": "linkedin",
                        "externalLink": "",
                        "assets": [
                            {
                                "source": "https://ptia.pt/assets/image.jpg",
                                "thumbnail": "",
                            }
                        ],
                    }
                }
            },
        ) as graphql:
            post = client.get_post("post_1")

        self.assertEqual(post.id, "post_1")
        self.assertEqual(post.status, "scheduled")
        self.assertEqual(post.text, "Real Buffer text")
        self.assertEqual(post.channel_service, "linkedin")
        self.assertEqual(post.asset_sources, ["https://ptia.pt/assets/image.jpg"])
        variables = graphql.call_args.args[1]
        self.assertEqual(variables["input"]["id"], "post_1")


if __name__ == "__main__":
    unittest.main()
