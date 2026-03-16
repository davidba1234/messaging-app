# Office Messenger - Testing Deployment Guide

This guide covers how to deploy the Office Messenger server and client specifically for a testing scenario using a Python virtual environment (venv) instead of Docker. For the full production Docker deployment, see `README.md`.

## Table of Contents
- [Server Deployment (Linux VM)](#server-deployment-linux-vm)
- [Client Deployment (Testing Mode)](#client-deployment-testing-mode)
- [Client Deployment (Windows executable)](#client-deployment-windows-executable)

---

## Server Deployment (Linux VM)

### How the System Works
1. **Server (`message_server.py`)**: A centralized FastAPI server acts as the message broker. It listens for WebSocket connections on port `8765`. All messages sent by a client go to the server, which then routes them to the intended recipient(s). If a recipient is offline, the message is queued in the SQLite database and delivered when they reconnect.
2. **Client (`message_client.py`)**: A PyQt6 desktop application running on user machines. It maintains a persistent WebSocket connection to the server. It reads the server's location from a local `messenger_config.ini` file.
3. **Database (`messenger.db`)**: An SQLite database automatically maintained by the server to store users, message histories, and delivery statuses.
4. **Groups (`groups.json`)**: A configuration file read by the server to determine group memberships.



For testing purposes on the Linux VM, we will run the server manually using a standalone virtual environment.

### Prerequisites
1. Ensure **Python 3.11** or newer is installed on the Linux VM.
2. Open port `8765` for incoming TCP connections on the VM's firewall:
   ```bash
   sudo ufw allow 8765/tcp
   ```

### Step-by-Step Server Setup
1. **Transfer the Code:** Copy the server implementation (`message_server.py`, `requirements.txt`) to a directory on your VM.
   ```bash
   mkdir -p ~/office-messenger-test
   # (Transfer files into this directory via SCP, FTP, or Git)
   cd ~/office-messenger-test
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize Data Files (Optional but Recommended):**
   The server will automatically create `messenger.db` and a default `groups.json` file inside the running directory. However, you can create `groups.json` manually if you wish to pre-configure user groups.

5. **Run the Server:**
   Start the FastAPI WebSocket server (this is handled inside `message_server.py`):
   ```bash
   python message_server.py
   ```
   *Note: The server will listen on `0.0.0.0:8765` occupying the current terminal session. To keep it running after you disconnect your SSH session during testing, you can run it via `tmux` or `screen`, or execute it in the background:*
   ```bash
   nohup python message_server.py &
   ```

---

## Client Deployment (Testing Mode)

If you are evaluating the client locally without building the `.exe` yet:

1. Create a virtual environment on your local Windows testing machine:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
2. Install the client requirements (specifically PyQt6 and websocket-client):
   ```bash
   pip install -r requirements.txt
   ```
3. Run the client:
   ```bash
   python message_client.py
   ```
   On first launch, the GUI will prompt you for the server's IP address (enter the IP of your testing Linux VM) and save it to `C:\Users\<YourUsername>\messenger_config.ini`.

---

## Client Deployment (Windows executable)

Once testing is complete, you can build the client into a standalone Windows executable to distribute to your test group.

### 1. Compiling to `.exe`
Ensure your local Windows machine's virtual environment is activated, then run:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --windowed message_client.py
```
This process generates a standalone `message_client.exe` in the `dist/` directory.

### 2. Distributing the Configuration File
Rather than prompting each tester with the fallback UI, you can pre-configure the server connection.

1. Create a template file named `messenger_config.ini` with the VM's IP address:
   ```ini
   [Server]
   host = 192.168.1.100  # <--- Change this to your test VM's IP
   ```
2. Distribute both the compiled `message_client.exe` and the `messenger_config.ini` file to the testers.
3. Instruct testers to copy `messenger_config.ini` directly into their home directory (`C:\Users\<TheirUsername>\`). The `.exe` itself can be run from anywhere, such as their Desktop.


### Daily Startup Actions

#### Server
Once deployed, the server should be running 24/7. No daily startup actions are required for the server itself unless the host machine is rebooted.
- **To check server status:** Use `ps aux | grep message_server.py` to see if the process is running. If it was started in `tmux` or `screen`, attach to the session to view logs.

#### Client
Users simply double-click the `message_client.exe`. The application will start, connect to the server in the background, and minimize to the Windows system tray. It should generally be started once when the user logs into their computer.

### Managing Groups

Groups are managed centrally on the server via the `groups.json` file. The client applications do not dictate group membership; they read the available groups from the server.

1. Locate `groups.json` in the same directory as your server script (`message_server.py`).
2. Edit the JSON file. The format is `"GroupName": ["user1", "user2"]`. 
3. The special character `"*"` means "Everyone in the database".
    ```json
    {
      "Everyone": ["*"],
      "Management": ["alice", "bob"],
      "Sales Support": ["charlie", "david", "eve"]
    }
    ```
4. **Important:** After modifying `groups.json`, you must restart the server for the changes to take effect. Stop the script (`Ctrl+C` or `kill`) and start it again.

---