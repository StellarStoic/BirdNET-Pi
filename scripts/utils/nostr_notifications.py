import asyncio
import html
import os
import socket
import time
from urllib.parse import quote

from .db import get_todays_count_for, get_this_weeks_count_for
from .helpers import get_settings

nostr_images = {}
nostr_species_last_notified = {}


def parse_relays(relays):
    # Normalize the user-provided relay list into websocket URLs.
    return [
        relay.strip()
        for relay in (relays or "").replace("\\n", "\n").replace("\r", "\n").replace(",", "\n").split("\n")
        if relay.strip().startswith(("wss://", "ws://"))
    ]


def render_nostr_template(template, detection, reason, listenurl, image_url=""):
    # Replace BirdNET-Pi notification variables with this detection's values.
    friendlyurl = f"[Listen here]({listenurl})"
    replacements = {
        "$sciname": detection["sci_name"],
        "$comname": detection["com_name"],
        "$confidencepct": str(detection["confidencepct"]),
        "$confidence": str(detection["confidence"]),
        "$listenurl": listenurl,
        "$friendlyurl": friendlyurl,
        "$date": str(detection["date"]),
        "$time": str(detection["time_of_day"]),
        "$week": str(detection["week"]),
        "$latitude": str(detection["latitude"]),
        "$longitude": str(detection["longitude"]),
        "$cutoff": str(detection["cutoff"]),
        "$sens": str(detection["sens"]),
        "$overlap": str(detection["overlap"]),
        "$reason": reason,
        "$image": image_url,
        "$flickrimage": image_url,
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def get_nostr_image_url(settings_dict, detection):
    # Fetch the selected Bird Photo Source image URL through BirdNET-Pi's local image API.
    if not settings_dict.get("IMAGE_PROVIDER"):
        return ""

    import requests

    com_name = detection["com_name"]
    if com_name not in nostr_images:
        try:
            sci_name = quote(detection["sci_name"])
            response = requests.get(url=f"http://localhost/api/v1/image/{sci_name}", timeout=10)
            response.raise_for_status()
            nostr_images[com_name] = response.json().get("data", {}).get("image_url", "")
        except Exception as e:
            print("NOSTR IMAGE API ERROR:", e)
            nostr_images[com_name] = ""
    return nostr_images.get(com_name, "")


def should_send_nostr(com_name, settings_dict):
    # Apply Nostr's standalone notification filters and rate limits.
    if settings_dict.get("NOSTR_DM_ENABLED") != "1":
        return False
    if not settings_dict.get("NOSTR_DM_RECIPIENT_NPUB"):
        return False
    if not settings_dict.get("NOSTR_DM_SENDER_NSEC"):
        return False
    if len(parse_relays(settings_dict.get("NOSTR_DM_RELAYS"))) == 0:
        return False

    excluded = settings_dict.get("NOSTR_DM_ONLY_NOTIFY_SPECIES_NAMES", "")
    if excluded.strip():
        excluded_species = [bird.lower().replace(" ", "") for bird in excluded.split(",")]
        if com_name.lower().replace(" ", "") in excluded_species:
            return False

    included = settings_dict.get("NOSTR_DM_ONLY_NOTIFY_SPECIES_NAMES_2", "")
    if included.strip():
        included_species = [bird.lower().replace(" ", "") for bird in included.split(",")]
        if com_name.lower().replace(" ", "") not in included_species:
            return False

    minimum_seconds = settings_dict.get("NOSTR_DM_MINIMUM_SECONDS_BETWEEN_NOTIFICATIONS_PER_SPECIES", "0")
    if minimum_seconds != "0" and nostr_species_last_notified.get(com_name) is not None:
        try:
            if int(time.time()) - nostr_species_last_notified[com_name] < int(minimum_seconds):
                return False
        except Exception as e:
            print("NOSTR NOTIFICATION EXCEPTION: " + str(e))
            return False

    return True


async def send_nip17_dm(sender_nsec, recipient_npub, relays, message):
    # Use nostr-sdk for NIP-17/NIP-44/NIP-59 crypto and relay publishing.
    try:
        from nostr_sdk import Client, Keys, NostrSigner, PublicKey, RelayUrl
    except ImportError as exc:
        raise RuntimeError("nostr-sdk is not installed in the BirdNET-Pi virtualenv") from exc

    keys = Keys.parse(sender_nsec)
    signer = NostrSigner.keys(keys)
    recipient = PublicKey.parse(recipient_npub)
    relay_urls = [RelayUrl.parse(relay) for relay in relays]
    client = Client(signer)

    for relay in relay_urls:
        await client.add_relay(relay)

    await client.connect()
    try:
        # send_private_msg_to sends a NIP-17 private message to specific relays.
        await client.send_private_msg_to(relay_urls, recipient, message, [])
    finally:
        await client.shutdown()


def send_nostr_dm(sender_nsec, recipient_npub, relays, message):
    # Provide a synchronous wrapper for BirdNET-Pi's analysis and test scripts.
    asyncio.run(send_nip17_dm(sender_nsec, recipient_npub, relays, message))


def format_nostr_message(settings_dict, detection, reason):
    # Build the final Nostr DM body from the standalone Nostr title/body templates.
    websiteurl = settings_dict.get("BIRDNETPI_URL")
    if websiteurl is None or len(websiteurl) == 0:
        websiteurl = f"http://{socket.gethostname()}.local"

    listenurl = f"{websiteurl}?filename={detection['path']}"
    title = html.unescape(settings_dict.get("NOSTR_DM_NOTIFICATION_TITLE", "New BirdNET-Pi Detection")).replace("\\n", "\n")
    body = html.unescape(settings_dict.get("NOSTR_DM_NOTIFICATION_BODY", "A $comname ($sciname) was detected with $confidencepct% confidence ($reason)")).replace("\\n", "\n")
    image_url = get_nostr_image_url(settings_dict, detection) if "$image" in title or "$image" in body or "$flickrimage" in title or "$flickrimage" in body else ""
    return (
        f"{render_nostr_template(title, detection, reason, listenurl, image_url)}\n\n"
        f"{render_nostr_template(body, detection, reason, listenurl, image_url)}"
    )


def notify_nostr(settings_dict, detection, reason):
    # Send one NIP-17 DM for a prepared detection notification reason.
    message = format_nostr_message(settings_dict, detection, reason)
    send_nostr_dm(
        settings_dict.get("NOSTR_DM_SENDER_NSEC"),
        settings_dict.get("NOSTR_DM_RECIPIENT_NPUB"),
        parse_relays(settings_dict.get("NOSTR_DM_RELAYS")),
        message,
    )
    nostr_species_last_notified[detection["com_name"]] = int(time.time())


def sendNostrNotifications(sci_name, com_name, confidence, confidencepct, path, date, time_of_day, week, latitude, longitude, cutoff, sens, overlap):
    # Mirror Apprise's notification reasons, but use standalone Nostr settings.
    settings_dict = get_settings()
    if not should_send_nostr(com_name, settings_dict):
        return

    detection = {
        "sci_name": sci_name,
        "com_name": com_name,
        "confidence": confidence,
        "confidencepct": confidencepct,
        "path": path,
        "date": date,
        "time_of_day": time_of_day,
        "week": week,
        "latitude": latitude,
        "longitude": longitude,
        "cutoff": cutoff,
        "sens": sens,
        "overlap": overlap,
    }

    if settings_dict.get("NOSTR_DM_NOTIFY_EACH_DETECTION") == "1":
        notify_nostr(settings_dict, detection, "detection")

    if settings_dict.get("NOSTR_DM_NOTIFY_NEW_SPECIES_EACH_DAY") == "1":
        numberDetections = get_todays_count_for(sci_name)
        if 0 < numberDetections <= 1:
            notify_nostr(settings_dict, detection, "first time today")

    if settings_dict.get("NOSTR_DM_NOTIFY_NEW_SPECIES") == "1":
        numberDetections = get_this_weeks_count_for(sci_name)
        if 0 < numberDetections <= 5:
            notify_nostr(settings_dict, detection, f"only seen {numberDetections} times in last 7d")


def generate_sender_keys():
    # Generate a dedicated BirdNET-Pi Nostr keypair for sending notifications.
    try:
        from nostr_sdk import Keys
    except ImportError as exc:
        raise RuntimeError("nostr-sdk is not installed in the BirdNET-Pi virtualenv") from exc

    keys = Keys.generate()
    return {
        "nsec": keys.secret_key().to_bech32(),
        "npub": keys.public_key().to_bech32(),
    }


def get_sender_npub(sender_nsec):
    # Derive the sender npub shown in the web UI from the stored nsec.
    if not sender_nsec:
        return ""
    try:
        from nostr_sdk import Keys
        return Keys.parse(sender_nsec).public_key().to_bech32()
    except Exception:
        return ""
