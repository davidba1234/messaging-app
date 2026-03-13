
```markdown

\# Office Messenger — Home Network Test Setup



\## Overview



A real-time internal messaging system with popup notifications, message

acknowledgement, and offline message queuing.



\### Network Layout



```

┌──────────────────┐     ┌──────────────┐     ┌──────────────────┐

│   COMPULSION      │     │     NUC      │     │  WINDOWS LAPTOP   │

│   Windows PC      │     │   Linux PC   │     │  (WiFi)           │

│   SERVER          │     │  CLIENT #1   │     │  CLIENT #2        │

│   192.168.x.x     │     │              │     │                   │

└────────┬──────────┘     └──────┬───────┘     └────────┬──────────┘

&nbsp;        │                       │                      │

&nbsp;   ─────┴───────────────────────┴──────────────────────┴──────

&nbsp;                        Home Router

```



---



\## Prerequisites



| Machine       | Needs                        |

|---------------|------------------------------|

| Compulsion    | Python 3.12+                 |

| NUC           | Python 3.10+, X11 or Wayland |

| Windows Laptop| Python 3.12+                 |



Install Python from https://www.python.org/downloads/



> \*\*Windows installs:\*\* You MUST tick \*\*"Add python.exe to PATH"\*\* during

> installation.



---



\## Step 1 — Find the Server IP



On \*\*Compulsion\*\*, open Command Prompt and run:



```batch

ipconfig

```



Note the \*\*IPv4 Address\*\* of your active network adapter, e.g. `192.168.1.50`.

This is referred to as `SERVER\_IP` throughout this guide.



---



\## Step 2 — Identify Client Usernames



On the \*\*NUC\*\* (Linux):



```bash

echo $USER

```



On the \*\*Windows Laptop\*\*:



```batch

echo %USERNAME%

```



Write both down. These are the names that appear in the contacts list and are

used in `groups.json`.



Example: NUC = `david`, Laptop = `sarah`



---



\## Step 3 — Set Up the Server (Compulsion)



\### 3.1 Create the project folder



```batch

mkdir C:\\OfficeMessenger\\server

cd C:\\OfficeMessenger\\server

```



\### 3.2 Create a virtual environment



```batch

python -m venv venv

venv\\Scripts\\activate

```



You should see `(venv)` at the start of the prompt.



\### 3.3 Install dependencies



```batch

pip install fastapi uvicorn\[standard] websockets

```



\### 3.4 Create server files



Place the following files in `C:\\OfficeMessenger\\server\\`:



\*\*`server.py`\*\* — the main server script (provided separately)



\*\*`groups.json`\*\* — defines message groups:



```json

{

&nbsp;   "Everyone": \["\*"],

&nbsp;   "Testers": \["david", "sarah"]

}

```



> Replace `david` and `sarah` with the real usernames from Step 2.



\### 3.5 Open the firewall



Open Command Prompt \*\*as Administrator\*\* and run:



```batch

netsh advfirewall firewall add rule name="Office Messenger" dir=in action=allow protocol=TCP localport=8765

```



\### 3.6 Start the server



```batch

cd C:\\OfficeMessenger\\server

venv\\Scripts\\activate

python server.py

```



Expected output:



```

\[DB] Initialized at C:\\OfficeMessenger\\server\\messenger.db

Server listening on 0.0.0.0:8765

INFO:     Uvicorn running on http://0.0.0.0:8765 (Press CTRL+C to quit)

```



\### 3.7 Verify the server is running



Open a browser on Compulsion and go to:



```

http://localhost:8765/health

```



You should see:



```json

{"status": "ok", "online": \[]}

```



> \*\*Leave the server command prompt open. Do not close it.\*\*



---



\## Step 4 — Set Up Client on NUC (Linux)



\### 4.1 Verify network connectivity



```bash

curl http://SERVER\_IP:8765/health

```



You should see `{"status":"ok","online":\[]}`. If not, check the firewall

rule on Compulsion (Step 3.5).



\### 4.2 Install system libraries



```bash

sudo apt install -y \\

&nbsp;   libxcb-cursor0 \\

&nbsp;   libxcb-xinerama0 \\

&nbsp;   libxcb-icccm4 \\

&nbsp;   libxcb-keysyms1 \\

&nbsp;   libxcb-render-util0 \\

&nbsp;   libxcb-shape0 \\

&nbsp;   libxkbcommon-x11-0 \\

&nbsp;   libgl1-mesa-glx \\

&nbsp;   libegl1

```



\### 4.3 Create the project folder



```bash

mkdir -p ~/messaging-app

cd ~/messaging-app

```



\### 4.4 Create a virtual environment



```bash

python3 -m venv venv

source venv/bin/activate

```



\### 4.5 Install Python dependencies



```bash

pip install PyQt6 websocket-client

```



\### 4.6 Create client files



Place these files in `~/messaging-app/`:



\*\*`message\_client.py`\*\* — the main client script (provided separately)



\*\*`client\_config.json`\*\*:



```json

{

&nbsp;   "server\_host": "SERVER\_IP",

&nbsp;   "server\_port": 8765

}

```



> Replace `SERVER\_IP` with the actual IP from Step 1, e.g. `"192.168.1.50"`



\### 4.7 Launch the client



```bash

cd ~/messaging-app

source venv/bin/activate

python3 message\_client.py

```



The messenger window appears. The server console should log:



```

\[+] david connected  (1 online)

```



---



\## Step 5 — Set Up Client on Windows Laptop



\### 5.1 Verify network connectivity



Open a browser and go to:



```

http://SERVER\_IP:8765/health

```



\### 5.2 Create the project folder



```batch

mkdir C:\\OfficeMessenger\\client

cd C:\\OfficeMessenger\\client

```



\### 5.3 Create a virtual environment



```batch

python -m venv venv

venv\\Scripts\\activate

```



\### 5.4 Install Python dependencies



```batch

pip install PyQt6 websocket-client

```



\### 5.5 Create client files



Place these files in `C:\\OfficeMessenger\\client\\`:



\*\*`message\_client.py`\*\* — the main client application (provided separately)



\*\*`client\_config.json`\*\*:



```json

{

&nbsp;   "server\_host": "SERVER\_IP",

&nbsp;   "server\_port": 8765

}

```



> Replace `SERVER\_IP` with the actual IP from Step 1.



\### 5.6 Launch the client



```batch

cd C:\\OfficeMessenger\\client

venv\\Scripts\\activate

python message\_client.py

```



The server console should now log:



```

\[+] sarah connected  (2 online)

```



---



\## Daily Usage



\### Starting the server (Compulsion)



```batch

cd C:\\OfficeMessenger\\server

venv\\Scripts\\activate

python server.py

```



\### Starting the client (NUC)



```bash

cd ~/messaging-app

source venv/bin/activate

python3 message\_client.py

```



\### Starting the client (Windows Laptop)



```batch

cd C:\\OfficeMessenger\\client

venv\\Scripts\\activate

python message\_client.py

```



\### Stopping



| Component      | How to stop                              |

|----------------|------------------------------------------|

| Server         | Press `Ctrl+C` in its command prompt     |

| Client (Linux) | Close the window or `Ctrl+C` in terminal |

| Client (Windows)| Close the window or press `Alt+F4`      |



---



\## Testing Checklist



\### Direct Message



1\. On the NUC — click `sarah` in the contacts list

2\. Type a message and press Enter

3\. On the Laptop — a popup notification appears

4\. Click \*\*Acknowledge\*\* on the popup

5\. On the NUC — status updates to Acknowledged



\### Reply



1\. When a popup appears, click \*\*Reply\*\*

2\. The main window opens with the sender selected

3\. Type a reply and press Enter

4\. The sender receives the reply as a popup



\### Group Message



1\. Click any group name (e.g. Everyone) in the contacts list

2\. Type a message and press Enter

3\. All members of that group receive the popup



\### Offline Delivery



1\. Close the client on the NUC

2\. On the Laptop — send a message to `david`

3\. Status shows sent (not yet delivered)

4\. Restart the client on the NUC

5\. The queued message pops up immediately

6\. Laptop status updates to delivered



\### Message History



1\. Send a few messages back and forth

2\. Close and reopen a client

3\. Click on a contact — previous messages load in the chat view



---



\## Folder Structure



\### Server (Compulsion)



```

C:\\OfficeMessenger\\server\\

├── venv\\                  ← virtual environment (auto-generated)

├── server.py              ← main server application

├── groups.json            ← group definitions

└── messenger.db           ← message database (auto-created on first run)

```



\### Client (NUC)



```

~/messaging-app/

├── venv/                  ← virtual environment

├── message\_client.py      ← main client application

└── client\_config.json     ← server connection settings

```



\### Client (Windows Laptop)



```

C:\\OfficeMessenger\\client\\

├── venv\\                  ← virtual environment

├── message\_client.py      ← main client application

└── client\_config.json     ← server connection settings

```



---



\## Troubleshooting



| Problem | Solution |

|---|---|

| `Python was not found` | Install Python and tick \*\*"Add to PATH"\*\* during install |

| Client shows Disconnected | Check `server\_host` in `client\_config.json`. Try opening `http://SERVER\_IP:8765/health` in a browser |

| Browser can't reach `/health` | Re-run the firewall rule on Compulsion (Step 3.5) as Administrator |

| NUC: `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Re-run Step 4.2 to install system libraries |

| `ModuleNotFoundError` | Activate the venv first: `venv\\Scripts\\activate` (Windows) or `source venv/bin/activate` (Linux) |

| Messages sent but no popup appears | Make sure the recipient username in `groups.json` matches exactly what `echo %USERNAME%` / `echo $USER` returns |

| Server crashes on startup | Check nothing else is using port 8765: `netstat -an | findstr 8765` |

| Popups disappear before being read | Remove the `QTimer.singleShot` line in the popup class in `message\_client.py` |



---



\## Ports and Protocols



| Port  | Protocol | Used For             |

|-------|----------|----------------------|

| 8765  | TCP/HTTP | REST API (health, history) |

| 8765  | TCP/WS   | WebSocket (real-time messaging) |



Only one port needs to be open on the server firewall.



---



\## Adding New Users



When a new PC connects, the server automatically sees the username. To include

them in message groups:



1\. Open `C:\\OfficeMessenger\\server\\groups.json` on Compulsion

2\. Add their username to the relevant groups

3\. The `"Everyone": \["\*"]` group automatically includes all connected users

&nbsp;  — no editing needed



> The server reads `groups.json` on each message send, so changes take effect

> immediately without restarting.



---



\## Resetting Everything



To start fresh (clear all message history):



1\. Stop the server (`Ctrl+C`)

2\. Delete the database:

&nbsp;  ```batch

&nbsp;  del C:\\OfficeMessenger\\server\\messenger.db

&nbsp;  ```

3\. Restart the server — a new empty database is created automatically

```

