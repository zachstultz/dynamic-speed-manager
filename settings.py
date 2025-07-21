# --- Configuration ---

# SABnzbd settings
SABNZBD_HOST = ""
SABNZBD_PORT = 8080
SABNZBD_API_KEY = ""

# Deluge settings
DELUGE_HOST = ""
DELUGE_PORT = 58846
DELUGE_USER = ""
DELUGE_PASSWORD = ""

# qBittorrent settings
QBITTORRENT_HOST = ""
QBITTORRENT_PORT = 8080
QBITTORRENT_USER = ""
QBITTORRENT_PASSWORD = ""

# Speed settings (in kB/s)
TOTAL_SPEED_LIMIT = 3000
DEFAULT_SPEED_LIMIT = 1000

# If present, the script will only check your download clients
# if there are files/folders in these directories, otherwise it will not check.
#
# Helps avoid unnecessary API calls when no downloads are present
watched_folder_paths = []
