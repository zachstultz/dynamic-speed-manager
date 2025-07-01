import time
import requests
from deluge_client import DelugeRPCClient
from qbittorrentapi import Client as qBittorrentClient
from qbittorrentapi.exceptions import APIConnectionError

from settings import *


# --- SABnzbd Functions ---


def is_sabnzbd_downloading():
    """Checks if SABnzbd has active downloads."""
    try:
        url = f"http://{SABNZBD_HOST}:{SABNZBD_PORT}/sabnzbd/api?mode=queue&apikey={SABNZBD_API_KEY}&output=json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("queue", {}).get("status") == "Downloading"
    except requests.exceptions.RequestException:
        # Silently fail if SABnzbd is offline
        return False
    except (KeyError, ValueError):
        print("\tError: Unexpected JSON from SABnzbd. Please check version/API.")
        return False


def set_sabnzbd_speed(speed):
    """Sets the download speed limit for SABnzbd in kB/s."""
    try:
        url = f"http://{SABNZBD_HOST}:{SABNZBD_PORT}/sabnzbd/api?mode=config&name=speedlimit&value={speed}K&apikey={SABNZBD_API_KEY}"
        requests.get(url, timeout=5).raise_for_status()
    except requests.exceptions.RequestException:
        # Silently fail if SABnzbd is offline
        pass


# --- Deluge Functions ---


def get_deluge_client():
    """Establishes a connection to the Deluge daemon."""
    try:
        client = DelugeRPCClient(
            DELUGE_HOST, DELUGE_PORT, DELUGE_USER, DELUGE_PASSWORD, decode_utf8=True
        )
        client.connect()
        print("Successfully connected to Deluge.")
        return client
    except Exception as e:
        # Catch any exception during connection and report it
        print(f"\tCould not connect to Deluge: {e}")
        return None


def is_deluge_downloading(client):
    """Checks if Deluge has active downloads."""
    if not client or not client.connected:
        return False
    try:
        torrents = client.call(
            "core.get_torrents_status", {"state": "Downloading"}, ["name"]
        )
        return bool(torrents)
    except Exception:
        # If any error occurs during the API call (e.g., connection dropped),
        # assume it's not downloading.
        return False


def set_deluge_speed(client, speed):
    """Sets the 'Throttled' download speed limit in the Scheduler plugin."""
    if not client or not client.connected:
        return
    try:
        client.call("scheduler.set_config", {"low_down": speed})
    except Exception:
        # Silently fail if setting the speed causes an error.
        # The main loop will handle the disconnected state.
        pass


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
        print("Successfully connected to qBittorrent.")
        return client
    except APIConnectionError as e:
        print(f"\tCould not connect to qBittorrent: {e}")
        return None
    except Exception as e:
        print(f"\tAn unexpected error occurred connecting to qBittorrent: {e}")
        return None


def is_qbittorrent_downloading(client):
    """Checks for actively downloading torrents, ignoring paused ones."""
    if not client:
        return False
    try:
        downloading_torrents = client.torrents_info(status_filter="downloading")
        if not downloading_torrents:
            return False
        for torrent in downloading_torrents:
            if torrent["state"] not in ["pausedDL", "stoppedDL"]:
                return True
        return False
    except APIConnectionError:
        return False


def set_qbittorrent_speed(client, speed):
    """Sets the download speed limit for qBittorrent in KiB/s."""
    if not client:
        return
    try:
        client.transfer_set_download_limit(speed * 1024)
    except APIConnectionError:
        pass


# --- Main Loop (Major changes here) ---


def main():
    """Main loop to monitor clients and adjust speeds with graceful reconnection."""
    print("Starting dynamic speed manager...")

    deluge_client = None
    qb_client = None
    previous_active_clients = []

    while True:
        try:
            # --- Proactive Connection Management ---
            # Check Deluge connection and reconnect if needed
            if not deluge_client or not deluge_client.connected:
                deluge_client = get_deluge_client()

            # Check qBittorrent connection and reconnect if needed
            is_qb_connected = False
            if qb_client:
                try:
                    # A lightweight API call to check if the connection is alive
                    _ = qb_client.app.version
                    is_qb_connected = True
                except APIConnectionError:
                    print("\tqBittorrent connection lost. Will attempt to reconnect.")

            if not is_qb_connected:
                qb_client = get_qbittorrent_client()

            # --- Status Checking ---
            active_clients = []
            if is_sabnzbd_downloading():
                active_clients.append("sabnzbd")
            if is_deluge_downloading(deluge_client):
                active_clients.append("deluge")
            if is_qbittorrent_downloading(qb_client):
                active_clients.append("qbittorrent")

            # --- Speed Adjustment Logic ---
            # Only update speeds if the state has changed to reduce API calls
            if active_clients == previous_active_clients:
                time.sleep(5)
                continue

            print(f"Active client state changed. New state: {active_clients or 'None'}")
            previous_active_clients = active_clients
            num_active = len(active_clients)

            speed_per_client = (
                TOTAL_SPEED_LIMIT // num_active
                if num_active > 0
                else DEFAULT_SPEED_LIMIT
            )

            print(
                f"\tApplying speed limit: {speed_per_client} kB/s for {num_active} client(s)"
            )

            # Set speeds for all clients based on the new state
            set_sabnzbd_speed(
                speed_per_client if "sabnzbd" in active_clients else DEFAULT_SPEED_LIMIT
            )
            set_deluge_speed(
                deluge_client,
                speed_per_client if "deluge" in active_clients else DEFAULT_SPEED_LIMIT,
            )
            set_qbittorrent_speed(
                qb_client,
                (
                    speed_per_client
                    if "qbittorrent" in active_clients
                    else DEFAULT_SPEED_LIMIT
                ),
            )

            time.sleep(5)

        except Exception as e:
            print(f"\tA critical error occurred in the main loop: {e}")
            print("\tRestarting loop in 15 seconds...")
            time.sleep(15)


if __name__ == "__main__":
    main()
