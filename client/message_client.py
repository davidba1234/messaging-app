# client/client.py
"""
Office Messenger — Client
Runs on each user's Windows PC.
"""

import sys
import os
import json
import html
import time
import socket
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTextBrowser, QTextEdit, QPushButton,
    QLabel, QSystemTrayIcon, QMenu, QSplitter, QMessageBox, QDialog,
    QFrame, QLineEdit, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import (
    QIcon, QColor, QFont, QAction, QPixmap, QPainter, QKeyEvent, QCloseEvent,
)

import websocket  # pip install websocket-client


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

import configparser

CONFIG_FILE = Path.home() / "messenger_config.ini"

def load_config() -> str:
    if not CONFIG_FILE.exists():
        return ""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get("Server", "host", fallback="")

def save_config(host: str):
    config = configparser.ConfigParser()
    config["Server"] = {"host": host}
    with open(CONFIG_FILE, "w") as f:
        config.write(f)

import getpass
try:
    USERNAME = os.environ.get("USERNAME") or os.getlogin()
except OSError:
    USERNAME = getpass.getuser()

# Get the Windows Computer Name (e.g., "SURGERY-PC")
COMPUTER_NAME = socket.gethostname()

# The unique technical ID for the server
UNIQUE_ID = f"{USERNAME}|{COMPUTER_NAME}"

HOST = load_config()
PORT = 8765

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messenger Configuration")
        self.setFixedSize(350, 150)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Welcome to Office Messenger!\nPlease enter the Server IP Address to connect."))
        
        form = QFormLayout()
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g. 192.168.0.109")
        form.addRow("Server IP:", self.ip_input)
        layout.addLayout(form)
        
        btn = QPushButton("Save && Connect")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def get_ip(self) -> str:
        return self.ip_input.text().strip()


# ═══════════════════════════════════════════════════════════════
# WebSocket background thread
# ═══════════════════════════════════════════════════════════════

class WebSocketThread(QThread):
    message_received = pyqtSignal(dict)
    connected        = pyqtSignal()
    disconnected     = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._ws: websocket.WebSocketApp | None = None
        self._running = True

    def run(self):
        url = f"ws://{HOST}:{PORT}/ws/{UNIQUE_ID}"
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                print(f"WS error: {e}")

            if self._running:
                self.disconnected.emit()
                time.sleep(5)

    def _on_open(self, ws):
        self.connected.emit()

    def _on_message(self, ws, raw):
        try:
            self.message_received.emit(json.loads(raw))
        except json.JSONDecodeError:
            pass

    def _on_close(self, ws, code, msg):
        self.disconnected.emit()

    def _on_error(self, ws, err):
        print(f"WS err: {err}")

    # Called from the MAIN thread — websocket-client's send() is thread-safe
    def send(self, payload: dict):
        if self._ws and self._ws.sock and self._ws.sock.connected:
            try:
                self._ws.send(json.dumps(payload))
            except Exception as e:
                print(f"Send err: {e}")

    def stop(self):
        self._running = False
        if self._ws:
            self._ws.close()


# ═══════════════════════════════════════════════════════════════
# Dictation thread (optional — needs SpeechRecognition + PyAudio)
# ═══════════════════════════════════════════════════════════════

class DictationThread(QThread):
    text_ready     = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            import speech_recognition as sr
            rec = sr.Recognizer()
            with sr.Microphone() as src:
                rec.adjust_for_ambient_noise(src, duration=0.5)
                audio = rec.listen(src, timeout=10, phrase_time_limit=30)
            self.text_ready.emit(rec.recognize_google(audio))
        except ImportError:
            self.error_occurred.emit(
                "Install dictation libs:\n"
                "pip install SpeechRecognition pyaudio"
            )
        except Exception as e:
            self.error_occurred.emit(str(e))


# ═══════════════════════════════════════════════════════════════
# Custom text input — Enter sends, Shift+Enter = new line
# ═══════════════════════════════════════════════════════════════

class MessageInput(QTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, ev: QKeyEvent):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(ev)
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(ev)


# ═══════════════════════════════════════════════════════════════
# Popup notification dialog
# ═══════════════════════════════════════════════════════════════

class PopupNotification(QDialog):
    acknowledged  = pyqtSignal(int)      # message_id
    typing_reply  = pyqtSignal(int)      # message_id
    reply_clicked = pyqtSignal(str, str) # sender username, group_name

    def __init__(self, sender: str, content: str, msg_id: int,
                 group_name: str = None, parent=None, main_window=None):
        super().__init__(parent)
        self.msg_id = msg_id
        self.sender = sender
        self.group_name = group_name
        self.main_window = main_window

        self.setWindowTitle("New Message")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(380)

        lo = QVBoxLayout(self)
        lo.setContentsMargins(16, 14, 16, 14)

        # header
        hdr = f"📨  {group_name}" if group_name else "📨  Direct Message"
        h = QLabel(hdr)
        h.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        h.setStyleSheet("color:#1a73e8;")
        lo.addWidget(h)

        lo.addWidget(QLabel(f"From:  {sender}"))

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#ddd;")
        lo.addWidget(line)

        body = QLabel(content[:500])
        body.setWordWrap(True)
        body.setFont(QFont("Segoe UI", 10))
        body.setStyleSheet("padding:8px 0;")
        lo.addWidget(body)

        btns = QHBoxLayout()

        ack = QPushButton("✅ Acknowledge")
        ack.setStyleSheet(
            "QPushButton{background:#34a853;color:white;border:none;"
            "padding:8px 14px;border-radius:4px;font-weight:bold;}"
            "QPushButton:hover{background:#2d9249;}"
        )
        ack.clicked.connect(self._ack)
        btns.addWidget(ack)

        rep = QPushButton("💬 Reply")
        rep.setStyleSheet(
            "QPushButton{background:#1a73e8;color:white;border:none;"
            "padding:8px 14px;border-radius:4px;font-weight:bold;}"
            "QPushButton:hover{background:#1557b0;}"
        )
        rep.clicked.connect(self._reply)
        btns.addWidget(rep)

        dismiss = QPushButton("✕")
        dismiss.setFixedSize(30, 30)
        dismiss.setStyleSheet(
            "QPushButton{background:#aaa;color:white;border:none;"
            "border-radius:15px;font-weight:bold;}"
            "QPushButton:hover{background:#777;}"
        )
        dismiss.clicked.connect(self.close)
        btns.addWidget(dismiss)

        lo.addLayout(btns)

        self.setStyleSheet(
            "QDialog{background:white;border:2px solid #1a73e8;border-radius:10px;}"
        )
        #QTimer.singleShot(CFG.get("popup_duration_ms", 15000), self.close)

    def _ack(self):
        self.acknowledged.emit(self.msg_id)
        if self.main_window:
            self.main_window.select_contact(self.sender, activate=False)
        self.close()

    def _reply(self):
        self.typing_reply.emit(self.msg_id)
        self.reply_clicked.emit(self.sender, self.group_name)
        self.close()


# ═══════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Office Messenger — {USERNAME}")
        self.setMinimumSize(900, 650)

        # state
        self.online_users: list[str] = []
        self.all_users:    list[str] = []
        self.groups:       list[str] = []
        self.current_chat: str | None = None
        self.chat_is_group = False
        self.popups: list[PopupNotification] = []

        self._build_ui()
        self._build_tray()
        self._start_ws()

    # ── build UI ─────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT — contact & group lists
        left = QWidget()
        left.setMinimumWidth(180)
        left.setMaximumWidth(270)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 4, 8)

        ll.addWidget(self._section_label("CONTACTS"))
        self.user_list = QListWidget()
        self.user_list.itemClicked.connect(self._pick_user)
        ll.addWidget(self.user_list, stretch=3)

        ll.addWidget(self._section_label("GROUPS"))
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self._pick_group)
        ll.addWidget(self.group_list, stretch=1)

        left.setStyleSheet("background:#f7f8fa;")
        splitter.addWidget(left)

        # RIGHT — chat area
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 8, 8, 8)

        self.chat_header = QLabel("Select a contact or group")
        self.chat_header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.chat_header.setStyleSheet("padding:8px;color:#333;")
        rl.addWidget(self.chat_header)

        self.chat_view = QTextBrowser()
        self.chat_view.setFont(QFont("Segoe UI", 10))
        self.chat_view.setOpenExternalLinks(False)
        rl.addWidget(self.chat_view, stretch=1)

        # compose row
        compose = QHBoxLayout()
        self.msg_input = MessageInput()
        self.msg_input.setMaximumHeight(80)
        self.msg_input.setPlaceholderText(
            "Type a message…   (Enter → send · Shift+Enter → new line)"
        )
        self.msg_input.setFont(QFont("Segoe UI", 10))
        self.msg_input.send_requested.connect(self._send)
        compose.addWidget(self.msg_input)

        bcol = QVBoxLayout()
        self.send_btn = QPushButton("Send  📤")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self._send)
        self.send_btn.setEnabled(False)
        bcol.addWidget(self.send_btn)

        self.dict_btn = QPushButton("Dictate 🎤")
        self.dict_btn.setFixedHeight(36)
        self.dict_btn.clicked.connect(self._dictate)
        bcol.addWidget(self.dict_btn)
        compose.addLayout(bcol)

        rl.addLayout(compose)

        self.status = QLabel("⏳ Connecting…")
        self.status.setFont(QFont("Segoe UI", 9))
        rl.addWidget(self.status)

        splitter.addWidget(right)
        splitter.setSizes([220, 680])
        main.addWidget(splitter)

        self.setStyleSheet("""
            QMainWindow{background:#fff;}
            QListWidget{border:1px solid #e0e0e0;border-radius:6px;outline:0;font-size:12px;}
            QListWidget::item{padding:8px 6px;border-bottom:1px solid #f0f0f0;}
            QListWidget::item:selected{background:#1a73e8;color:white;border-radius:4px;}
            QTextBrowser{border:1px solid #e0e0e0;border-radius:6px;padding:8px;background:#fafbfc;}
            QTextEdit{border:1px solid #e0e0e0;border-radius:6px;padding:6px;}
            QPushButton{background:#1a73e8;color:white;border:none;padding:8px 16px;
                        border-radius:6px;font-size:11px;font-weight:bold;}
            QPushButton:hover{background:#1557b0;}
            QPushButton:disabled{background:#b0b0b0;}
        """)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lb = QLabel(f"  {text}")
        lb.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lb.setStyleSheet("color:#888;padding-top:4px;")
        return lb

    # ── system tray ──────────────────────────────────────────

    def _build_tray(self):
        px = QPixmap(32, 32)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#1a73e8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "M")
        p.end()

        icon = QIcon(px)
        self.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        a1 = QAction("Open Messenger", self); a1.triggered.connect(self._raise)
        menu.addAction(a1)
        menu.addSeparator()
        a2 = QAction("Quit", self); a2.triggered.connect(self._quit)
        menu.addAction(a2)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._raise()
            if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.setToolTip(f"Office Messenger — {USERNAME}")
        self.tray.show()

    # ── websocket ────────────────────────────────────────────

    def _start_ws(self):
        self.ws = WebSocketThread()
        self.ws.message_received.connect(self._on_msg)
        self.ws.connected.connect(lambda: self._set_conn(True))
        self.ws.disconnected.connect(lambda: self._set_conn(False))
        self.ws.start()

    def _set_conn(self, ok: bool):
        if ok:
            self.status.setText("🟢  Connected")
            self.status.setStyleSheet("color:#34a853;")
        else:
            self.status.setText("🔴  Disconnected — reconnecting…")
            self.status.setStyleSheet("color:#ea4335;")

    # ── contact selection ────────────────────────────────────

    def _pick_user(self, item: QListWidgetItem):
        self.group_list.clearSelection()
        user = item.data(Qt.ItemDataRole.UserRole)
        self.current_chat = user
        self.chat_is_group = False
        dot = "🟢" if user in self.online_users else "⚪"
        self.chat_header.setText(f"{dot}  Chat with {user}")
        self.send_btn.setEnabled(True)
        self.status.setText("")
        self.ws.send({"type": "history_request", "with_user": user})

    def _pick_group(self, item: QListWidgetItem):
        self.user_list.clearSelection()
        grp = item.data(Qt.ItemDataRole.UserRole)
        self.current_chat = grp
        self.chat_is_group = True
        self.chat_header.setText(f"👥  Group: {grp}")
        self.send_btn.setEnabled(True)
        self.status.setText("")
        self.ws.send({"type": "history_request", "with_group": grp})

    # ── sending ──────────────────────────────────────────────

    def _send(self):
        text = self.msg_input.toPlainText().strip()
        if not text or not self.current_chat:
            return

        payload = {"type": "message", "content": text}
        if self.chat_is_group:
            payload["group_name"] = self.current_chat
            payload["recipient"] = None
        else:
            payload["recipient"] = self.current_chat
            payload["group_name"] = None

        self.ws.send(payload)
        self._bubble("You", text, datetime.now().strftime("%H:%M"), mine=True)
        self.msg_input.clear()

    # ── dictation ────────────────────────────────────────────

    def _dictate(self):
        self.dict_btn.setText("🔴 Listening…")
        self.dict_btn.setEnabled(False)
        self._dt = DictationThread()
        self._dt.text_ready.connect(lambda t: self.msg_input.insertPlainText(t))
        self._dt.error_occurred.connect(
            lambda e: QMessageBox.warning(self, "Dictation Error", e)
        )
        self._dt.finished.connect(self._dict_reset)
        self._dt.start()

    def _dict_reset(self):
        self.dict_btn.setText("Dictate 🎤")
        self.dict_btn.setEnabled(True)

    # ── incoming server messages ─────────────────────────────

    def _on_msg(self, data: dict):
        t = data.get("type")

        if t == "user_list":
            self._refresh_lists(data)

        elif t == "message":
            self._on_incoming(data)

        elif t == "message_sent":
            st = data.get("status", "sent")
            if st == "delivered":
                label = "✓✓ Sent but not yet seen"
            elif st == "queued":
                label = "📥 Queued (recipient offline)"
            elif st == "acknowledged":
                label = "✅ Acknowledged"
            else:
                label = "✓ Sent"
            self.status.setText(label)

        elif t == "status_update":
            by = data.get("acknowledged_by", "")
            st = data.get("status", "")
            
            # Don't show status update if viewing another direct chat
            if by and not self.chat_is_group and self.current_chat != by:
                return

            icons = {"delivered": "✓✓ Sent but not yet seen",
                     "acknowledged": f"✅ Acknowledged by {by}",
                     "typing_reply": f"✍️ {by} is typing a reply"}
            self.status.setText(icons.get(st, st))

        elif t == "history_response":
            self._show_history(data)

    def _refresh_lists(self, data: dict):
        self.online_users = data.get("online_users", [])
        self.all_users    = data.get("all_users", [])
        self.groups       = data.get("groups", [])

        sel = self.current_chat if not self.chat_is_group else None

        self.user_list.clear()
        for full_id in sorted(self.all_users):
            if full_id == UNIQUE_ID:
                continue
            
            # Split "nurses|ROOM-101" into ["nurses", "ROOM-101"]
            if "|" in full_id:
                name, room = full_id.split("|", 1)
                display_text = f"{name} ({room})"
            else:
                display_text = full_id # Fallback for old/simple IDs

            on = full_id in self.online_users
            it = QListWidgetItem(f" {'🟢' if on else '⚪'}  {display_text}")
            it.setData(Qt.ItemDataRole.UserRole, full_id)
            
            if not on:
                it.setForeground(QColor("#a0a0a0"))
                font = it.font()
                font.setItalic(True)
                it.setFont(font)
                
            self.user_list.addItem(it)
            if full_id == sel:
                it.setSelected(True)

        self.group_list.clear()
        for g in self.groups:
            it = QListWidgetItem(f" 📋  {g}")
            it.setData(Qt.ItemDataRole.UserRole, g)
            self.group_list.addItem(it)

    def _on_incoming(self, data: dict):
        sender_raw = data["sender"]
        if "|" in sender_raw:
            sender_display, room = sender_raw.split("|", 1)
            sender_name = f"{sender_display} ({room})"
        else:
            sender_name = sender_raw

        content   = data["content"]
        msg_id    = data["id"]
        grp       = data.get("group_name")
        ts        = data.get("timestamp", "")
        time_str  = datetime.now().strftime("%H:%M")
        if ts:
            try:
                time_str = datetime.fromisoformat(ts).strftime("%H:%M")
            except Exception:
                pass

        # Is the user currently looking at this conversation AND is the app active/focused?
        viewing = (
            (not grp and self.current_chat == sender_raw and not self.chat_is_group)
            or (grp and self.current_chat == grp and self.chat_is_group)
        )

        if viewing:
            self._bubble(sender_name, content, time_str, mine=False)
            if self.status.text() == f"✍️ {sender_raw} is typing a reply":
                self.status.setText("")
            
        self._popup(sender_raw, content, msg_id, grp)

    def _show_history(self, data: dict):
        self.chat_view.clear()
        for m in data.get("messages", []):
            mine = m["sender"] == UNIQUE_ID
            ts = m.get("timestamp", "")
            time_str = datetime.now().strftime("%d-%m-%Y %H:%M")
            if ts:
                try:
                    time_str = datetime.fromisoformat(ts).strftime("%d-%m-%Y %H:%M")
                except Exception:
                    pass
            
            grp = m.get("group_name")
            sender_raw = m["sender"]
            if "|" in sender_raw:
                sender_display, room = sender_raw.split("|", 1)
                sender_name = f"{sender_display} ({room})"
            else:
                sender_name = sender_raw

            if grp and not mine:
               name = f"{sender_name} ({grp})"
            else:
               name = "You" if mine else sender_name

            self._bubble(name, m["content"], time_str, mine=mine, status=m.get("status",""))

    # ── chat bubbles ─────────────────────────────────────────

    def _bubble(self, name: str, text: str, time_str: str,
                mine: bool, status: str = ""):
        bg    = "#4caf50" if mine else "#d4edda"
        fg    = "white"   if mine else "black"
        align = "right"   if mine else "left"
        st    = {"sent":"✓","delivered":"✓✓","acknowledged":"✅","queued":"📥"}.get(status,"")
        safe  = html.escape(text).replace("\n", "<br>")

        self.chat_view.append(f"""
        <div style="text-align:{align};margin:4px 8px;">
          <div style="display:inline-block;background:{bg};color:{fg};
                      padding:8px 14px;border-radius:14px;max-width:65%;
                      text-align:left;font-size:13px;">
            <b style="font-size:11px;">{html.escape(name)}</b>
            <span style="font-size:9px;opacity:.7;"> {time_str}</span><br>
            {safe}
            <span style="font-size:9px;opacity:.7;"> {st}</span>
          </div>
        </div>""")
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── popup notifications ──────────────────────────────────

    def _popup(self, sender, content, msg_id, grp):
        # self.tray.showMessage(
        #     f"Message from {sender}" + (f" ({grp})" if grp else ""),
        #     content[:150],
        #     QSystemTrayIcon.MessageIcon.Information, 5000,
        # )

        if len(self.popups) >= 3:
            # We already have 3 popups, just acknowledge silently for the UI
            # to prevent freezing, or leave it in the tray.
            return
            
        pop = PopupNotification(sender, content, msg_id, grp, main_window=self)
        pop.acknowledged.connect(
            lambda mid: self.ws.send({"type": "acknowledge", "message_id": mid})
        )
        pop.typing_reply.connect(
            lambda mid: self.ws.send({"type": "typing_reply", "message_id": mid})
        )
        pop.reply_clicked.connect(self._jump_to)

        screen = QApplication.primaryScreen().availableGeometry()
        offset = len(self.popups) * (pop.sizeHint().height() + 10)
        pop.move(screen.right() - pop.width() - 20,
                 screen.bottom() - pop.sizeHint().height() - 20 - offset)
        pop.show()
        pop.finished.connect(lambda: (
            self.popups.remove(pop) if pop in self.popups else None
        ))
        self.popups.append(pop)

    def select_contact(self, username, activate=True):
        """Select a contact in the list and load their conversation."""
        for i in range(self.user_list.count()):
            item = self.user_list.item(i)
            if item.text() == username or item.data(Qt.ItemDataRole.UserRole) == username:
                self.user_list.setCurrentItem(item)
                self._pick_user(item)
                break
        
        if activate:
            self._raise()

    def _jump_to(self, username: str, group_name: str = None):
        if group_name:
            for i in range(self.group_list.count()):
                it = self.group_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == group_name:
                    self.group_list.setCurrentItem(it)
                    self._pick_group(it)
                    break
        else:
            for i in range(self.user_list.count()):
                it = self.user_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == username:
                    self.user_list.setCurrentItem(it)
                    self._pick_user(it)
                    break

        self._raise()
        self.msg_input.setFocus()

    # ── window management ────────────────────────────────────

    def _raise(self):
        self.show()
        if self.isMinimized():
            self.setWindowState(Qt.WindowState.WindowNoState)
            self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, ev: QCloseEvent):
        ev.ignore()
        self.hide()
        self.tray.showMessage(
            "Office Messenger",
            "Still running — double-click the tray icon to open.",
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )

    def _quit(self):
        self.ws.stop()
        self.ws.wait(3000)
        QApplication.quit()


# ═══════════════════════════════════════════════════════════════
# Launch
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Office Messenger")
    app.setStyle("Fusion")

    if not HOST:
        dialog = ConfigDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_host = dialog.get_ip()
            if new_host:
                save_config(new_host)
                HOST = new_host
            else:
                sys.exit(0)
        else:
            sys.exit(0)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())