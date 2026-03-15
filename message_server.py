# server/server.py
"""
Office Messenger — Server
Run on your always-on server: python server.py
"""

import json
import sqlite3
import aiosqlite
import html
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

DATABASE_PATH = Path(__file__).parent / "messenger.db"
GROUPS_FILE   = Path(__file__).parent / "groups.json"
HOST = "0.0.0.0"      # Listen on all interfaces
PORT = 8765

# Configure logging
LOG_FILE = Path(__file__).parent / "server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        TimedRotatingFileHandler(LOG_FILE, when="D", interval=1, backupCount=7),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Database Layer
# ═══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn

async def get_db_async():
    conn = await aiosqlite.connect(str(DATABASE_PATH))
    conn.row_factory = aiosqlite.Row
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
            group_name   TEXT DEFAULT NULL,
            content      TEXT NOT NULL,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS message_recipients (
            msg_id       INTEGER NOT NULL,
            recipient    TEXT NOT NULL,
            status       TEXT DEFAULT 'sent',
            FOREIGN KEY(msg_id) REFERENCES messages(id)
        );

        CREATE INDEX IF NOT EXISTS idx_msg_recipient
            ON message_recipients(recipient, status);

        CREATE INDEX IF NOT EXISTS idx_msg_conversation
            ON messages(sender, timestamp);
    """)
    conn.commit()
    conn.close()
    logger.info(f"[DB] Initialized at {DATABASE_PATH}")


async def db_register_user(username: str):
    async with await get_db_async() as conn:
        now = datetime.now().isoformat()
        await conn.execute("""
            INSERT INTO users (username, last_seen) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET last_seen = ?
        """, (username, now, now))
        await conn.commit()


async def db_all_users() -> list[str]:
    async with await get_db_async() as conn:
        async with conn.execute("SELECT username FROM users ORDER BY username") as cursor:
            rows = await cursor.fetchall()
            return [r["username"] for r in rows]


async def db_save_message(sender: str, recipients: list[str], content: str,
                    group_name: Optional[str] = None) -> int:
    async with await get_db_async() as conn:
        now = datetime.now().isoformat()
        cursor = await conn.execute("""
            INSERT INTO messages (sender, group_name, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (sender, group_name, content, now))
        msg_id = cursor.lastrowid
        
        await conn.executemany("""
            INSERT INTO message_recipients (msg_id, recipient, status)
            VALUES (?, ?, 'sent')
        """, [(msg_id, r) for r in recipients])
        
        await conn.commit()
        return msg_id


async def db_update_status(message_id: int, status: str, recipient: Optional[str] = None):
    async with await get_db_async() as conn:
        if recipient:
            await conn.execute("UPDATE message_recipients SET status = ? WHERE msg_id = ? AND recipient = ?", (status, message_id, recipient))
        else:
            await conn.execute("UPDATE message_recipients SET status = ? WHERE msg_id = ?", (status, message_id))
        await conn.commit()


async def db_get_message(message_id: int) -> Optional[dict]:
    async with await get_db_async() as conn:
        async with conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def db_get_undelivered(username: str) -> list[dict]:
    async with await get_db_async() as conn:
        async with conn.execute("""
            SELECT m.id, m.sender, m.group_name, m.content, m.timestamp, r.recipient, r.status
            FROM messages m
            JOIN message_recipients r ON m.id = r.msg_id
            WHERE r.recipient = ? AND r.status IN ('sent', 'queued')
            ORDER BY m.timestamp
        """, (username,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def db_get_history(user1: str, user2: str, limit: int = 100) -> list[dict]:
    async with await get_db_async() as conn:
        async with conn.execute("""
            SELECT m.id, m.sender, m.group_name, m.content, m.timestamp, r.recipient, r.status
            FROM messages m
            JOIN message_recipients r ON m.id = r.msg_id
            WHERE ((m.sender=? AND r.recipient=?) OR (m.sender=? AND r.recipient=?))
              AND m.group_name IS NULL
            ORDER BY m.timestamp DESC
            LIMIT ?
        """, (user1, user2, user2, user1, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]


async def db_get_group_history(group_name: str, limit: int = 100) -> list[dict]:
    async with await get_db_async() as conn:
        async with conn.execute("""
            SELECT id, sender, group_name, content, timestamp
            FROM messages
            WHERE group_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (group_name, limit)) as cursor:
            rows = await cursor.fetchall()
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


async def resolve_group_members(group_name: str) -> list[str]:
    groups = load_groups()
    if group_name not in groups:
        return []
    members = groups[group_name]
    if "*" in members:
        return await db_all_users()      # Everyone
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
        
        # Check for multiple logins
        if username in self.active:
            old_ws = self.active[username]
            try:
                await old_ws.send_json({"type": "error", "message": "Logged in from another location"})
                await old_ws.close()
            except Exception:
                pass
            logger.info(f"[!] Closed older connection for {username}")
        
        self.active[username] = ws
        await db_register_user(username)
        logger.info(f"[+] {username} connected  ({len(self.active)} online)")
        await self.broadcast_user_list()
        await self._flush_queue(username)

    async def disconnect(self, username: str):
        self.active.pop(username, None)
        logger.info(f"[-] {username} disconnected  ({len(self.active)} online)")
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
        all_users = await db_all_users()
        payload = {
            "type":         "user_list",
            "online_users": list(self.active.keys()),
            "all_users":    all_users,
            "groups":       list(load_groups().keys()),
        }
        for ws in list(self.active.values()):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def _flush_queue(self, username: str):
        """Push every undelivered message to a user who just came online."""
        undelivered = await db_get_undelivered(username)
        for msg in undelivered:
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
                await db_update_status(msg["id"], "delivered", username)
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
    logger.info(f"Server listening on {HOST}:{PORT}")


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
        try:
           await websocket.send_json({"type": "error", "message": "Invalid format or error"})
        except Exception:
           pass
        logger.exception(f"[!] Error ({username}): {exc}")
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

    elif t == "typing_reply":
        await _handle_typing_reply(sender, data)

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
        members = await resolve_group_members(group_name)
        recipients = [m for m in members if m != sender]
        if not recipients:
             return
             
        msg_id = await db_save_message(sender, recipients, content, group_name)
        for member in recipients:
            ok = await mgr.send_to(member, {
                "type": "message", "id": msg_id,
                "sender": sender, "recipient": member,
                "group_name": group_name, "content": content,
                "timestamp": datetime.now().isoformat(),
            })
            if ok:
                await db_update_status(msg_id, "delivered", member)

        await mgr.send_to(sender, {
            "type": "message_sent", "group_name": group_name, "status": "sent"
        })

    elif recipient:
        # ── Direct message ──
        msg_id = await db_save_message(sender, [recipient], content)
        ok = await mgr.send_to(recipient, {
            "type": "message", "id": msg_id,
            "sender": sender, "recipient": recipient,
            "group_name": None, "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        status = "delivered" if ok else "queued"
        await db_update_status(msg_id, status, recipient)
        await mgr.send_to(sender, {
            "type": "message_sent", "message_id": msg_id,
            "recipient": recipient, "status": status,
        })


async def _handle_ack(sender: str, data: dict):
    msg_id = data.get("message_id")
    if not msg_id:
        return
    await db_update_status(msg_id, "acknowledged", sender)
    msg = await db_get_message(msg_id)
    if msg:
        await mgr.send_to(msg["sender"], {
            "type": "status_update",
            "message_id": msg_id,
            "status": "acknowledged",
            "acknowledged_by": sender,
        })


async def _handle_typing_reply(sender: str, data: dict):
    msg_id = data.get("message_id")
    if not msg_id:
        return
    await db_update_status(msg_id, "acknowledged", sender)
    msg = await db_get_message(msg_id)
    if msg:
        await mgr.send_to(msg["sender"], {
            "type": "status_update",
            "message_id": msg_id,
            "status": "typing_reply",
            "acknowledged_by": sender,
        })


async def _handle_history(sender: str, data: dict):
    group = data.get("with_group")
    if group:
        history = await db_get_group_history(group)
        await mgr.send_to(sender, {
            "type":       "history_response",
            "with_group": group,
            "messages":   history,
        })
        return

    other = data.get("with_user")
    if not other:
        return
    history = await db_get_history(sender, other)
    await mgr.send_to(sender, {
        "type":      "history_response",
        "with_user": other,
        "messages":  history,
    })


# ═══════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")