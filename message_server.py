# server/server.py
"""
Office Messenger — Server
Run on your always-on server: python server.py
"""

import json
import sqlite3
import html
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

DATABASE_PATH = Path(__file__).parent / "messenger.db"
GROUPS_FILE   = Path(__file__).parent / "groups.json"
HOST = "0.0.0.0"      # Listen on all interfaces
PORT = 8765


# ═══════════════════════════════════════════════════════════════
# Database Layer
# ═══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username     TEXT PRIMARY KEY,
            first_seen   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sender       TEXT NOT NULL,
            recipient    TEXT NOT NULL,
            group_name   TEXT DEFAULT NULL,
            content      TEXT NOT NULL,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status       TEXT DEFAULT 'sent'
        );

        CREATE INDEX IF NOT EXISTS idx_msg_recipient
            ON messages(recipient, status);

        CREATE INDEX IF NOT EXISTS idx_msg_conversation
            ON messages(sender, recipient, timestamp);
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Initialized at {DATABASE_PATH}")


def db_register_user(username: str):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO users (username, last_seen) VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET last_seen = ?
    """, (username, now, now))
    conn.commit()
    conn.close()


def db_all_users() -> list[str]:
    conn = get_db()
    rows = conn.execute("SELECT username FROM users ORDER BY username").fetchall()
    conn.close()
    return [r["username"] for r in rows]


def db_save_message(sender: str, recipient: str, content: str,
                    group_name: Optional[str] = None) -> int:
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO messages (sender, recipient, content, group_name, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (sender, recipient, content, group_name, datetime.now().isoformat()))
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def db_update_status(message_id: int, status: str):
    conn = get_db()
    conn.execute("UPDATE messages SET status = ? WHERE id = ?", (status, message_id))
    conn.commit()
    conn.close()


def db_get_message(message_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_get_undelivered(username: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM messages
        WHERE recipient = ? AND status = 'sent'
        ORDER BY timestamp
    """, (username,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_get_history(user1: str, user2: str, limit: int = 100) -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM messages
        WHERE ((sender=? AND recipient=?) OR (sender=? AND recipient=?))
          AND group_name IS NULL
        ORDER BY timestamp DESC
        LIMIT ?
    """, (user1, user2, user2, user1, limit)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ═══════════════════════════════════════════════════════════════
# Groups (loaded from JSON config file)
# ═══════════════════════════════════════════════════════════════

def load_groups() -> dict:
    if not GROUPS_FILE.exists():
        default = {
            "Everyone": ["*"],
            "Management": [],
            "Sales": []
        }
        GROUPS_FILE.write_text(json.dumps(default, indent=2))
        return default
    return json.loads(GROUPS_FILE.read_text())


def resolve_group_members(group_name: str) -> list[str]:
    groups = load_groups()
    if group_name not in groups:
        return []
    members = groups[group_name]
    if "*" in members:
        return db_all_users()      # Everyone
    return members


# ═══════════════════════════════════════════════════════════════
# Connection Manager — tracks every connected client
# ═══════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    # ── connect / disconnect ─────────────────────────────────

    async def connect(self, username: str, ws: WebSocket):
        await ws.accept()
        self.active[username] = ws
        db_register_user(username)
        print(f"[+] {username} connected  ({len(self.active)} online)")
        await self.broadcast_user_list()
        await self._flush_queue(username)

    async def disconnect(self, username: str):
        self.active.pop(username, None)
        print(f"[-] {username} disconnected  ({len(self.active)} online)")
        await self.broadcast_user_list()

    # ── send helpers ─────────────────────────────────────────

    async def send_to(self, username: str, payload: dict) -> bool:
        ws = self.active.get(username)
        if ws:
            try:
                await ws.send_json(payload)
                return True
            except Exception:
                return False
        return False

    async def broadcast_user_list(self):
        payload = {
            "type":         "user_list",
            "online_users": list(self.active.keys()),
            "all_users":    db_all_users(),
            "groups":       list(load_groups().keys()),
        }
        for ws in list(self.active.values()):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def _flush_queue(self, username: str):
        """Push every undelivered message to a user who just came online."""
        for msg in db_get_undelivered(username):
            ok = await self.send_to(username, {
                "type":       "message",
                "id":         msg["id"],
                "sender":     msg["sender"],
                "recipient":  msg["recipient"],
                "group_name": msg["group_name"],
                "content":    msg["content"],
                "timestamp":  msg["timestamp"],
            })
            if ok:
                db_update_status(msg["id"], "delivered")
                await self.send_to(msg["sender"], {
                    "type":       "status_update",
                    "message_id": msg["id"],
                    "status":     "delivered",
                })


mgr = ConnectionManager()


# ═══════════════════════════════════════════════════════════════
# FastAPI app + WebSocket endpoint
# ═══════════════════════════════════════════════════════════════

app = FastAPI(title="Office Messenger Server")


@app.on_event("startup")
async def startup():
    init_database()
    load_groups()
    print(f"Server listening on {HOST}:{PORT}")


@app.get("/health")
async def health():
    return {"status": "ok", "online": list(mgr.active.keys())}


@app.websocket("/ws/{username}")
async def ws_endpoint(websocket: WebSocket, username: str):
    await mgr.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await route(username, data)
    except WebSocketDisconnect:
        await mgr.disconnect(username)
    except Exception as exc:
        print(f"[!] Error ({username}): {exc}")
        await mgr.disconnect(username)


# ═══════════════════════════════════════════════════════════════
# Message routing
# ═══════════════════════════════════════════════════════════════

async def route(sender: str, data: dict):
    t = data.get("type")

    if t == "message":
        await _handle_message(sender, data)

    elif t == "acknowledge":
        await _handle_ack(sender, data)

    elif t == "history_request":
        await _handle_history(sender, data)


async def _handle_message(sender: str, data: dict):
    content    = (data.get("content") or "").strip()
    group_name = data.get("group_name")
    recipient  = data.get("recipient")
    if not content:
        return

    if group_name:
        # ── Group message → fan-out ──
        members = resolve_group_members(group_name)
        for member in members:
            if member == sender:
                continue
            msg_id = db_save_message(sender, member, content, group_name)
            ok = await mgr.send_to(member, {
                "type": "message", "id": msg_id,
                "sender": sender, "recipient": member,
                "group_name": group_name, "content": content,
                "timestamp": datetime.now().isoformat(),
            })
            if ok:
                db_update_status(msg_id, "delivered")

        await mgr.send_to(sender, {
            "type": "message_sent", "group_name": group_name, "status": "sent"
        })

    elif recipient:
        # ── Direct message ──
        msg_id = db_save_message(sender, recipient, content)
        ok = await mgr.send_to(recipient, {
            "type": "message", "id": msg_id,
            "sender": sender, "recipient": recipient,
            "group_name": None, "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        status = "delivered" if ok else "sent"
        db_update_status(msg_id, status)
        await mgr.send_to(sender, {
            "type": "message_sent", "message_id": msg_id,
            "recipient": recipient, "status": status,
        })


async def _handle_ack(sender: str, data: dict):
    msg_id = data.get("message_id")
    if not msg_id:
        return
    db_update_status(msg_id, "acknowledged")
    msg = db_get_message(msg_id)
    if msg:
        await mgr.send_to(msg["sender"], {
            "type": "status_update",
            "message_id": msg_id,
            "status": "acknowledged",
            "acknowledged_by": sender,
        })


async def _handle_history(sender: str, data: dict):
    other = data.get("with_user")
    if not other:
        return
    await mgr.send_to(sender, {
        "type":      "history_response",
        "with_user": other,
        "messages":  db_get_history(sender, other),
    })


# ═══════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")