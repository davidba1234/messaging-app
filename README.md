# Office Messenger

Office Messenger is a real-time, lightweight client-server messaging application designed for local and corporate networks. It features a FastAPI/WebSocket server with an SQLite backend, and a rich desktop client built with PyQt5. This README covers the architecture, deployment, and GitHub sync workflow for both the server and the client.

## Table of Contents
- [System Architecture](#system-architecture)
- [Keeping the System Up to Date (GitHub Sync Workflow)](#keeping-the-system-up-to-date-github-sync-workflow)
- [Server Deployment (Linux VM)](#server-deployment-linux-vm)
- [Client Deployment (Windows executable)](#client-deployment-windows-executable)
- [License](#license)

## System Architecture

The application is split into two independent parts:

### How the System Works
1. **Server (`message_server.py`)**: A centralized FastAPI server acts as the message broker. It listens for WebSocket connections on port `8765`. All messages sent by a client go to the server, which then routes them to the intended recipient(s). If a recipient is offline, the message is queued in the SQLite database and delivered when they reconnect.
2. **Client (`message_client.py`)**: A PyQt5 desktop application running on user machines. It maintains a persistent WebSocket connection to the server. It reads the server's location from a local `messenger_config.ini` file.
3. **Database (`messenger.db`)**: An SQLite database automatically maintained by the server to store users, message histories, and delivery statuses.
4. **Groups (`groups.json`)**: A configuration file read by the server to determine group memberships.



### 1. Server (`message_server.py`)
- **Frameworks:** Built on **FastAPI** and **Uvicorn**, utilizing **WebSockets** for real-time duplex communication.
- **Database Layer:** Uses `aiosqlite` and `sqlite3` to handle asynchronous read/writes to `messenger.db`. It tracks users, message history, and delivery statuses. Features queueing for messages sent to offline users.
- **Connection Management:** Tracks active connections and dynamically routes messages (both Direct and Group chats).
- **Groups Configuration:** Group definitions are loaded dynamically from `groups.json`.
- **Dockerized:** Packaged with a `Dockerfile` and `docker-compose.yml` for straightforward, reproducible deployments.

### 2. Client (`message_client.py`)
- **Frameworks:** A desktop GUI application built with **PyQt5** and `websocket-client`.
- **Configuration:** Reads the server's IP address from a configuration file `messenger_config.ini` in the user's home directory.
- **Multi-threaded Operations:** Uses a background `QThread` to maintain the WebSocket connection without freezing or lagging the GUI.
- **Rich Notifications:** Sits in the system tray and displays temporary, non-intrusive pop-up notifications (bottom right) when new messages arrive while the app is unfocused.
- **Features:** Group chats, delivery status receipts (Sent/Delivered/Acknowledged), message history via WebSocket requests, and optional microphone dictation integration.

---

## Server Deployment (Linux VM)

Follow these steps for a step-by-step deployment on a new hardware VM running Linux.

### Prerequisites
1. Ensure **Docker** and **Docker Compose** are installed on the Linux VM.
2. Open port `8765` for incoming TCP connections on the VM's firewall:
   ```bash
   sudo ufw allow 8765/tcp
   ```

### Step-by-Step Deployment
1. **Transfer the Code:** Copy the server files (`message_server.py`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`) to a directory on your VM.
   ```bash
   mkdir -p /opt/office-messenger
   # (Transfer files into this directory via SCP, FTP, or Git)
   cd /opt/office-messenger
   ```
2. **Create Empty Data Files:** The `docker-compose.yml` file uses bind mounts for `messenger.db` and `groups.json`. You must create them manually first to ensure Docker binds them as files, not automatically-created directories.
   ```bash
   touch messenger.db
   echo "{}" > groups.json
   ```
3. **Start the Server:** Containerize and start the application in detached mode.
   ```bash
   docker compose up -d --build
   ```
4. **Verify Deployment:** Check the logs to ensure the server started successfully and isn't throwing errors.
   ```bash
   docker compose logs -f
   ```
5. **Configure Groups (Optional):** Edit `groups.json` on the host to define user groups.
   ```json
   {
     "Everyone": ["*"],
     "Management": ["alice", "bob"]
   }
   ```
   Restart the server afterwards to apply group changes: `docker compose restart`.

---

## Client Deployment (Windows executable)

The client is designed to run natively on user workstations (typically Windows). Since distributing Python sets is cumbersome, you will convert the `message_client.py` into a monolithic `.exe`.

### 1. Compiling to `.exe`
Run this on a machine with Python installed to compile the client.

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconsole --onefile --windowed message_client.py
```
This generates a standalone `message_client.exe` in the `dist/` folder.

### 2. The Configuration File (`.ini`)
The compiled client application searches the user's home directory for `messenger_config.ini` (e.g., `C:\Users\<TheirUsername>\messenger_config.ini`). This file instructs the client on what Server IP to connect to.

If the file is completely missing, the client has a fallback GUI widget that will ask the user to type in the valid Server IP on the first launch and generate the file for them. However, to deploy it easily without requiring an IP manually from each user, you should pre-configure the `.ini` file.

Create a template file named `messenger_config.ini`:
```ini
[Server]
host = 192.168.1.100  # <--- Change this to your new Linux VM's IP address
```

### 3. Distributing to Users
When rolling this out to users:
1. Provide the end-user with a `.zip` file containing **both** the compiled `message_client.exe` and your pre-configured `messenger_config.ini`.
2. Instruct the user (or use a deployment script/GPO) to copy `messenger_config.ini` into their home directory (`C:\Users\<TheirUsername>\`). 
3. The `message_client.exe` can be placed anywhere (e.g., their Desktop or Documents folder) and double-clicked to run.

---

### Daily Startup Actions

#### Server
Once deployed (either via Docker or systemd), the server should be running 24/7. No daily startup actions are required for the server itself unless the host machine is rebooted (and the service isn't set to auto-start).
- **To check server status:** `docker compose logs --tail=50` (if using Docker) or `systemctl status office-messenger` (if using a system service).

#### Client
Users simply double-click the `message_client.exe`. The application will start, connect to the server in the background, and minimize to the Windows system tray. It should generally be started once when the user logs into their computer.

### Managing Groups

Groups are managed centrally on the server via the `groups.json` file. The client applications do not dictate group membership; they read the available groups from the server.

1. Locate `groups.json` in the same directory as your server script (or the mapped Docker volume).
2. Edit the JSON file. The format is `"GroupName": ["user1", "user2"]`. 
3. The special character `"*"` means "Everyone in the database".
    ```json
    {
      "Everyone": ["*"],
      "Management": ["alice", "bob"],
      "Sales Support": ["charlie", "david", "eve"]
    }
    ```
4. **Important:** After modifying `groups.json`, you must restart the server for the changes to take effect.
    - If using Docker: `docker compose restart`
    - If running directly: Stop the script (`Ctrl+C`) and start it again.


---

## Keeping the System Up to Date (GitHub Sync Workflow)

GitHub (`davidba1234/messaging-app`, branch `main`) is the central source of truth between your development machine (NUC), the Linux server VM, and the Windows client build folder.

### 1. Making Code Changes (on the NUC)
Before editing, pull the latest changes (including any version bumps from Windows client builds):
```bash
git pull origin main
```
After making and testing your changes, commit and push them to GitHub:
```bash
git add <changed-files>
git commit -m "Describe your change"
git push origin main
```

### 2. Updating the Server (Linux VM `10.0.1.247`)
Whenever `server/` files (such as `message_server.py`, `groups.json`, or `locations.json`) are updated on GitHub:
1. Connect to the work VPN from the NUC:
   ```bash
   sudo systemctl start netbird
   sudo netbird up --disable-dns
   ```
2. SSH into the server VM:
   ```bash
   ssh -p 2270 david@10.0.1.247
   ```
3. Run the sync command, which pulls `origin/main` into `/opt/office-messenger/server` and rebuilds/restarts the Docker container:
   ```bash
   messenger-sync
   ```
4. Exit the VM and disconnect NetBird when finished:
   ```bash
   exit
   sudo netbird down
   ```

### 3. Updating the Client (Windows PC)
Because PyInstaller on Linux cannot cross-compile a Windows `.exe`, the client executable is built on a Windows PC:
1. On the work Windows PC, open `H:\mydocs\OfficeMessenger\messaging-app\client\`.
2. Double-click **`Runcompilescript.bat`** (which runs `build_and_deploy.ps1`).
3. The script automatically:
   - Pulls the latest code from GitHub (`git pull origin main`).
   - Increments the version number in `client/file_version_info.txt`.
   - Compiles `message_client.py` into `message_client.exe` using the Windows `venv`.
   - Copies the new `message_client.exe` to `N:\OfficeMessenger\message_client.exe` for users.
   - Commits and pushes the updated `client/file_version_info.txt` back to GitHub.

---

## License
This project is licensed under the MIT License.