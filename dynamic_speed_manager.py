import time
import requests
from deluge_client import DelugeRPCClient
from qbittorrentapi import Client as qBittorrentClient

from settings import *


# --- SABnzbd Functions ---


def is_sabnzbd_downloading():
    """Checks if SABnzbd has active downloads."""
    try:
        # Use mode=queue which is the standard way to get queue information
        url = f"http://{SABNZBD_HOST}:{SABNZBD_PORT}/sabnzbd/api?mode=queue&apikey={SABNZBD_API_KEY}&output=json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        # The 'queue' object contains the 'status' key
        # We check if this status is 'Downloading'
        return data.get("queue", {}).get("status") == "Downloading"
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to SABnzbd: {e}")
        return False
    except KeyError:
        # This handles cases where the JSON response structure is unexpected
        print(
            "Error: Unexpected JSON structure from SABnzbd API. Please check your SABnzbd version and API."
        )
        return False


def set_sabnzbd_speed(speed):
    """Sets the download speed limit for SABnzbd in kB/s."""
    try:
        url = f"http://{SABNZBD_HOST}:{SABNZBD_PORT}/sabnzbd/api?mode=config&name=speedlimit&value={speed}K&apikey={SABNZBD_API_KEY}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error setting SABnzbd speed: {e}")


# --- Deluge Functions ---


def get_deluge_client():
    """Establishes a connection to the Deluge daemon."""
    try:
        client = DelugeRPCClient(DELUGE_HOST, DELUGE_PORT, DELUGE_USER, DELUGE_PASSWORD)
        client.connect()
        return client
    except Exception as e:
        print(f"Error connecting to Deluge: {e}")
        return None


def is_deluge_downloading(client):
    """Checks if Deluge has active downloads."""
    if not client:
        return False
    try:
        torrents = client.call(
            "core.get_torrents_status", {"state": "Downloading"}, ["name"]
        )
        return bool(torrents)
    except Exception as e:
        print(f"Error checking Deluge status: {e}")
        return False


def set_deluge_speed(client, speed):
    """
    Sets the 'Throttled' download speed limit in the Scheduler plugin.

    Note: The Scheduler plugin must be enabled in Deluge.
    """
    if not client:
        return
    try:
        # Deluge expects speed in KiB/s
        # We call the scheduler's specific config method
        client.call("scheduler.set_config", {"low_down": speed})
    except Exception as e:
        # This error will often happen if the Scheduler plugin is not enabled
        print(f"Error setting Deluge Scheduler speed: {e}")
        print("Please ensure the Scheduler plugin is enabled in Deluge's preferences.")


# --- qBittorrent Functions ---


def get_qbittorrent_client():
    """Establishes a connection to the qBittorrent client."""
    try:
        client = qBittorrentClient(
            host=QBITTORRENT_HOST,
            port=QBITTORRENT_PORT,
            username=QBITTORRENT_USER,
            password=QBITTORRENT_PASSWORD,
        )
        client.auth_log_in()
        return client
    except Exception as e:
        print(f"Error connecting to qBittorrent: {e}")
        return None


def is_qbittorrent_downloading(client):
    """
    Checks if qBittorrent has torrents that are actively downloading or stalled,
    ignoring those that are manually paused.
    """
    if not client:
        return False
    try:
        # Get all torrents that are in the 'downloading' category
        downloading_torrents = client.torrents_info(status_filter="downloading")

        # If the list is empty, nothing is downloading
        if not downloading_torrents:
            return False

        # Check if any of these torrents are not paused
        for torrent in downloading_torrents:
            # The state 'pausedDL' indicates a torrent that is in the downloading
            # category but has been manually paused. 'downloading' and 'stalledDL'
            # are considered active download attempts.
            if torrent["state"] not in ["pausedDL", "stoppedDL"]:
                # Found at least one torrent that is actively trying to download
                return True

        # If we looped through all torrents and they are all paused, return False
        return False

    except Exception as e:
        print(f"Error checking qBittorrent status: {e}")
        return False


def set_qbittorrent_speed(client, speed):
    """Sets the download speed limit for qBittorrent in KiB/s."""
    if not client:
        return
    try:
        # qBittorrent expects speed in bytes/s, so convert from kB/s
        client.transfer_set_download_limit(speed * 1024)
    except Exception as e:
        print(f"Error setting qBittorrent speed: {e}")


# --- Main Loop ---


def main():
    """Main loop to monitor clients and adjust speeds."""

    print("Starting dynamic speed manager...")

    deluge_client = get_deluge_client()
    qb_client = get_qbittorrent_client()
    previous_active_clients = []

    while True:
        try:
            active_clients = []
            if is_sabnzbd_downloading():
                active_clients.append("sabnzbd")
            if is_deluge_downloading(deluge_client):
                active_clients.append("deluge")
            if is_qbittorrent_downloading(qb_client):
                active_clients.append("qbittorrent")

            if active_clients and active_clients == previous_active_clients:
                time.sleep(5)
                continue

            previous_active_clients = active_clients

            num_active = len(active_clients)

            if num_active > 0:
                speed_per_client = TOTAL_SPEED_LIMIT // num_active
            else:
                speed_per_client = DEFAULT_SPEED_LIMIT

            print(
                f"Active clients: {num_active}. Speed per client: {speed_per_client} kB/s"
            )

            if "sabnzbd" in active_clients:
                set_sabnzbd_speed(speed_per_client)
            else:
                set_sabnzbd_speed(DEFAULT_SPEED_LIMIT)

            if "deluge" in active_clients:
                set_deluge_speed(deluge_client, speed_per_client)
            else:
                set_deluge_speed(deluge_client, DEFAULT_SPEED_LIMIT)

            if "qbittorrent" in active_clients:
                set_qbittorrent_speed(qb_client, speed_per_client)
            else:
                set_qbittorrent_speed(qb_client, DEFAULT_SPEED_LIMIT)

        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            # Attempt to reconnect if clients are not available
            if not deluge_client or not deluge_client.connected:
                deluge_client = get_deluge_client()
            if not qb_client or not qb_client.app.version:
                qb_client = get_qbittorrent_client()

        time.sleep(5)  # Check every 10 seconds


if __name__ == "__main__":
    main()
