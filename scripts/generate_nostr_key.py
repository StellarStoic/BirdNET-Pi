import argparse
import json

from utils.nostr_notifications import generate_sender_keys, get_sender_npub


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-from-nsec", default="")
    args = parser.parse_args()

    # Print sender key information as JSON for the settings UI.
    if args.public_from_nsec:
        print(json.dumps({"npub": get_sender_npub(args.public_from_nsec)}))
    else:
        print(json.dumps(generate_sender_keys()))
