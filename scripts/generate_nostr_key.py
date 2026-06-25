import json

from utils.nostr_notifications import generate_sender_keys


if __name__ == "__main__":
    # Print a dedicated BirdNET-Pi Nostr keypair as JSON for the settings UI.
    print(json.dumps(generate_sender_keys()))
