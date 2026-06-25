import argparse
import sys

from utils.nostr_notifications import sendNostrOperationalNotification


def build_tor_message(event, onion_url):
    # Build the operational DM body that tells the user which Tor onion address is current.
    if event == "reset":
        action = "A new Tor onion address was created for this BirdNET-Pi."
    elif event == "restart":
        action = "The Tor onion service was restarted for this BirdNET-Pi."
    else:
        action = "The Tor onion service was enabled for this BirdNET-Pi."

    return (
        f"{action}\n\n"
        f"Latest onion address:\n{onion_url}\n\n"
        "Use Tor Browser to open this address. Keep this DM private because it points to your BirdNET-Pi dashboard."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=["enable", "restart", "reset"], required=True)
    parser.add_argument("--onion", required=True)
    args = parser.parse_args()

    # Send a Tor address update without using detection templates or notification filters.
    sent = sendNostrOperationalNotification(
        "BirdNET-Pi Tor onion address updated",
        build_tor_message(args.event, args.onion),
    )

    if sent:
        print("Nostr Tor address DM submitted to configured relays.")
        sys.exit(0)

    print("Nostr Tor address DM skipped because Nostr DMs are not enabled or configured.")
    sys.exit(0)
