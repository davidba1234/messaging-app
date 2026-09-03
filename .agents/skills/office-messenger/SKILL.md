---
name: office-messenger
description: >-
  Comprehensive guide and reference for the Office Messenger application.
  Use when developing, modifying, building, debugging, or deploying the Office Messenger
  server, desktop client, user/group configurations, workstation location mappings, or database.
---

# Office Messenger System Guide & Knowledge Base

Office Messenger is a real-time, lightweight client-server messaging application designed for Katikati Medical Centre (KMC). It enables instant messaging across clinical rooms, nursing stations, reception, and administrative offices.

---

## 1. Directory Structure & Key Files

```text
messaging-app/
├── README.md                      # General system overview and deployment instructions
├── StartupSSH.txt                 # Remote VM connection (NetBird VPN + SSH) and sync guide
├── format_names.py                # Helper script for parsing and cleaning user names
├── names.txt                      # Raw names input file
├── server/
│   ├── message_server.py          # FastAPI/WebSocket server with aiosqlite/sqlite3 backend
│   ├── messenger.db               # SQLite database (users, messages, delivery statuses)
│   ├── locations.json             # Workstation hostname -> Room name mapping
│   ├── groups.json                # User group definitions (Doctors, Nurses, Admin, etc.)
│   ├── delete_user.py             # Utility to remove a user from the database
│   ├── Dockerfile                 # Docker configuration for Linux VM deployment
│   ├── docker-compose.yml         # Container compose config with volume mounts
│   └── requirements.txt           # Python dependencies for the server
├── client/
│   ├── message_client.py          # PyQt5/PyQt6 desktop client application
│   ├── build_and_deploy.ps1       # Automated version bumping, PyInstaller build & deployment to N: drive
│   ├── Runcompilescript.bat       # Wrapper batch file to run build_and_deploy.ps1
│   ├── file_version_info.txt      # Windows executable metadata & version tracking
│   ├── output/
│   │   └── message_client.exe     # Standalone compiled Windows executable
│   └── requirements.txt           # Python dependencies for the client
└── .agents/skills/office-messenger/
    └── SKILL.md                   # This skill definition
```

---

## 2. System Architecture & Workflows

### A. Server (`server/message_server.py`)
- **Framework**: FastAPI + Uvicorn listening on port `8765`.
- **Protocol**: WebSocket endpoint at `/ws/{UNIQUE_ID}` and REST endpoints (`/health`, `/locations`).
- **Database**: SQLite (`server/messenger.db`) using `aiosqlite` for async operations.
  - **Tables**: `users` (usernames, timestamps), `messages` (id, sender, group, content, parent_id, timestamp), `message_recipients` (msg_id, recipient, status).
- **Timezone**: All timestamps use `Pacific/Auckland` timezone.
- **Offline Message Queue**: If a recipient is offline, messages are stored with status `'sent'`. When the user reconnects, queued messages are automatically pushed and marked as `'delivered'`.
- **User Groups (`server/groups.json`)**: Predefined role groups (`Doctors`, `Management`, `Nurses`, `Admin`).
- **Workstation Locations (`server/locations.json`)**: Maps PC hostnames (e.g., `KMC114PC`, `KMC068PC`) to room names (e.g., `Prep Room`, `Room 1`).

### B. Client (`client/message_client.py`)
- **Framework**: PyQt5 / PyQt6 with `websocket-client` running in a dedicated `QThread`.
- **Identity & Identification**:
  - Technical ID format: `UNIQUE_ID = f"{USERNAME}|{room_name}|{WIN_USERNAME}"`
  - Resolves `room_name` dynamically by fetching `/locations` from the server and matching `socket.gethostname().lower()`.
  - For shared Windows accounts (`reception`, `admin`, `nurse`, `officenurse`, `office`), displays a `LoginDialog` allowing the staff member to enter their display name.
- **Config**: Reads server IP/hostname from `messenger_config.ini` in the user's home directory (`C:\Users\<Username>\messenger_config.ini`). Defaults to `messenger.katimed.co.nz`.
- **UI & Notifications**: Sits in system tray, plays sounds/popups for incoming messages, displays online/offline user lists, threaded replies, and message delivery statuses (sent / delivered / read).

---

## 3. Standard Procedures & Runbooks

### A. Updating Workstation Locations (`locations.json`)
1. Open `server/locations.json`.
2. Ensure keys match the exact computer hostname (case-insensitive lookup is used, but standard format is `KMCxxxPC`).
3. Ensure no trailing descriptions are in the key names unless intentional.
4. Push changes to GitHub and sync the server VM.

### B. Updating User Groups (`groups.json`)
1. Edit `server/groups.json`.
2. Add or remove usernames under the appropriate group category (`Doctors`, `Nurses`, `Admin`, `Management`).
3. Push to GitHub and sync the server VM.

### C. Building & Deploying the Windows Client (`.exe`)
1. Run `client/Runcompilescript.bat` or execute in PowerShell:
   ```powershell
   cd H:\mydocs\OfficeMessenger\messaging-app\client
   .\build_and_deploy.ps1
   ```
2. What this script does automatically:
   - Activates local virtual environment (`.\venv\Scripts\Activate.ps1`).
   - Auto-increments the patch version in `client/file_version_info.txt`.
   - Compiles a single-file `.exe` using PyInstaller into `client/output/message_client.exe`.
   - Copies `message_client.exe` to the shared network drive: `N:\OfficeMessenger\message_client.exe`.
   - Displays a Windows tray notification on completion.

### D. Syncing & Deploying the Server (Linux VM)
Refer to `StartupSSH.txt`:
1. Connect via NetBird VPN:
   ```bash
   sudo systemctl start netbird
   sudo netbird up --disable-dns
   ```
2. SSH to the work Debian VM:
   ```bash
   ssh -p 2270 david@10.0.1.247
   ```
3. Run the sync command:
   ```bash
   messenger-sync
   ```
   *(Pulls latest commits from GitHub `main`, rebuilds the Docker container via `docker compose up -d --build`, and restarts the server)*.
4. Disconnect:
   ```bash
   exit
   sudo netbird down
   ```
