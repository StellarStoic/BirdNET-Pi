import argparse
import datetime
import logging
import sys

from utils import nostr_notifications
from utils.db import get_latest
from utils.helpers import get_settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--sender", required=True)
    parser.add_argument("--relays", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    args = parser.parse_args()

    # Log to stdout so the web UI can show the exact success or failure.
    logger = logging.getLogger()
    formatter = logging.Formatter("[%(name)s][%(levelname)s] %(message)s")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    conf = get_settings()
    conf["NOSTR_DM_ENABLED"] = "1"
    conf["NOSTR_DM_RECIPIENT_NPUB"] = args.recipient
    conf["NOSTR_DM_SENDER_NSEC"] = args.sender
    conf["NOSTR_DM_RELAYS"] = args.relays
    conf["NOSTR_DM_NOTIFICATION_TITLE"] = args.title
    conf["NOSTR_DM_NOTIFICATION_BODY"] = args.body
    conf["NOSTR_DM_NOTIFY_EACH_DETECTION"] = "1"
    conf["NOSTR_DM_NOTIFY_NEW_SPECIES_EACH_DAY"] = "0"
    conf["NOSTR_DM_NOTIFY_NEW_SPECIES"] = "0"

    d = get_latest()
    if not d:
        now = datetime.datetime.now()
        d = {
            "Sci_Name": "Aptenodytes patagonicus",
            "Com_Name": "King Penguin",
            "Confidence": 0.84,
            "File_Name": "this_is_not_a_file.mp3",
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
            "Week": now.isocalendar()[1],
            "Lat": conf.getfloat("LATITUDE"),
            "Lon": conf.getfloat("LONGITUDE"),
            "Cutoff": conf.getfloat("CONFIDENCE"),
            "Sens": conf.getfloat("SENSITIVITY"),
            "Overlap": conf.getfloat("OVERLAP"),
        }

    # Send a sample NIP-17 DM using the latest detection when available.
    nostr_notifications.sendNostrNotifications(
        d["Sci_Name"],
        d["Com_Name"],
        d["Confidence"],
        round(d["Confidence"] * 100),
        d["File_Name"],
        d["Date"],
        d["Time"],
        d["Week"],
        d["Lat"],
        d["Lon"],
        d["Cutoff"],
        d["Sens"],
        d["Overlap"],
    )
    print("Nostr test DM submitted to configured relays.")
