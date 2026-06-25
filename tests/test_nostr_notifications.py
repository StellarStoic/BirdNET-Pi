import unittest
from unittest.mock import patch

from scripts.utils import nostr_notifications
from scripts.utils.nostr_notifications import format_nostr_message, parse_relays, sendNostrNotifications, should_send_nostr

from tests.helpers import Settings


class TestNostrNotifications(unittest.TestCase):

    def setUp(self):
        nostr_notifications.nostr_species_last_notified = {}

    def get_default_params(self):
        # Build one detection payload that mirrors the Apprise notification tests.
        return {
            "sci_name": "Myiarchus crinitus",
            "com_name": "Great Crested Flycatcher",
            "confidence": "0.91",
            "confidencepct": "91",
            "path": "filename",
            "date": "1666-06-06",
            "time_of_day": "06:06:06",
            "week": "06",
            "latitude": "-1",
            "longitude": "-1",
            "cutoff": "0.7",
            "sens": "1.25",
            "overlap": "0.0"
        }

    def get_enabled_settings(self):
        # Return a minimal enabled Nostr configuration without a real private key.
        settings = Settings.with_defaults()
        settings["NOSTR_DM_ENABLED"] = "1"
        settings["NOSTR_DM_RECIPIENT_NPUB"] = "npub1recipient"
        settings["NOSTR_DM_SENDER_NSEC"] = "nsec1sender"
        settings["NOSTR_DM_RELAYS"] = "wss://relay.example,wss://relay2.example"
        return settings

    def test_parse_relays(self):
        self.assertEqual(
            parse_relays("wss://relay.example, https://bad.example\nws://local.example"),
            ["wss://relay.example", "ws://local.example"]
        )

    def test_should_send_nostr_requires_enabled_config(self):
        settings = Settings.with_defaults()
        self.assertFalse(should_send_nostr("Great Crested Flycatcher", settings))

        settings = self.get_enabled_settings()
        self.assertTrue(should_send_nostr("Great Crested Flycatcher", settings))

    def test_format_nostr_message(self):
        settings = self.get_enabled_settings()
        settings["BIRDNETPI_URL"] = "http://birdnetpi.local"
        settings["NOSTR_DM_NOTIFICATION_BODY"] = "$comname $listenurl"
        msg = format_nostr_message(settings, self.get_default_params(), "detection")
        self.assertIn("New BirdNET-Pi Detection", msg)
        self.assertIn("Great Crested Flycatcher", msg)
        self.assertIn("http://birdnetpi.local?filename=filename", msg)

    @patch("scripts.utils.helpers._load_settings")
    @patch("scripts.utils.nostr_notifications.send_nostr_dm")
    def test_send_nostr_each_detection(self, mock_send, mock_load_settings):
        settings = self.get_enabled_settings()
        settings["NOSTR_DM_NOTIFY_EACH_DETECTION"] = "1"
        mock_load_settings.return_value = settings

        sendNostrNotifications(**self.get_default_params())

        self.assertEqual(mock_send.call_count, 1)
        self.assertIn("Great Crested Flycatcher", mock_send.call_args_list[0][0][3])

    @patch("scripts.utils.helpers._load_settings")
    @patch("scripts.utils.nostr_notifications.send_nostr_dm")
    def test_nostr_filters_included_species(self, mock_send, mock_load_settings):
        settings = self.get_enabled_settings()
        settings["NOSTR_DM_NOTIFY_EACH_DETECTION"] = "1"
        settings["NOSTR_DM_ONLY_NOTIFY_SPECIES_NAMES_2"] = "Northern Cardinal"
        mock_load_settings.return_value = settings

        sendNostrNotifications(**self.get_default_params())

        self.assertEqual(mock_send.call_count, 0)


if __name__ == "__main__":
    unittest.main()
