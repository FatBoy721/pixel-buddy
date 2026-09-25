"""The text box you type into and the cards that show what he found."""

import subprocess
import sys
from datetime import datetime
from html import escape

from desktop import show_everywhere
from web import browser_url

from PySide6.QtCore import QFileInfo, QMimeData, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QFileIconProvider, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

MONO = "Menlo" if sys.platform == "darwin" else "Consolas"
STYLE = f"""
    QFrame#panel {{
        background: #fff8ec; border: 3px solid #3a1014; border-radius: 10px;
    }}
    QLabel, QLineEdit, QListWidget, QPushButton {{ font-family: {MONO}; color: #3a1014; }}
    QLabel#title {{ font-size: 14px; font-weight: bold; }}
    QLineEdit {{
        background: white; border: 2px solid #3a1014; border-radius: 6px;
        padding: 6px; font-size: 13px;
    }}
    QListWidget {{ background: white; border: 2px solid #3a1014; border-radius: 6px; font-size: 12px; }}
    QListWidget::item {{ padding: 4px; }}
    QListWidget::item:selected {{ background: #ffd9c7; color: #3a1014; }}
    QPushButton {{
        background: #e2442e; color: white; border: 2px solid #3a1014; border-radius: 6px;
        padding: 5px 12px; font-weight: bold;
    }}
    QPushButton:hover {{ background: #ff805c; }}
    QPushButton#close {{ background: transparent; color: #3a1014; border: none; padding: 0 4px; }}
"""
PREVIEW_H = 200
FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool


def reveal_in_folder(path):
    """Open Finder / Explorer with the file selected."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{path}"])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def open_file(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def item_url(result):
    """A file hit or a web hit, as a QUrl (for opening or dragging out)."""
    return QUrl(result.url) if hasattr(result, "url") else QUrl.fromLocalFile(str(result.path))


class Panel(QWidget):
    """Frameless, always-on-top window with the crab-styled rounded panel."""

    def __init__(self):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame(objectName="panel")
        outer.addWidget(self.panel)
        self.body = QVBoxLayout(self.panel)
        self.body.setContentsMargins(12, 10, 12, 12)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: show_everywhere(self))  # also over full-screen apps

    def show_beside(self, near):
        """near: QRect of the crab window. Sit next to him, bottom-aligned, on-screen."""
        self.adjustSize()
        screen = (self.screen() or self.window().screen()).availableGeometry()
        x = near.right() + 8
        if x + self.width() > screen.right():
            x = near.left() - self.width() - 8
        self.move(max(screen.left(), x), screen.bottom() - self.height() - 20)
        self.show()
        self.raise_()

    def close_card(self):
        self.hide()
        self.closed.emit()


class InputBox(Panel):
    """The little box you type into. His answers go in his speech bubble.
    Stays open for back-and-forth; hides itself after a quiet spell."""
    sent = Signal(str)
    closed = Signal()
    IDLE_HIDE_MS = 30_000

    def __init__(self):
        super().__init__()
        self.setFixedWidth(360)
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="Talk to him… (Esc to close)")
        self.input.returnPressed.connect(self._submit)
        self.input.textEdited.connect(lambda _text: self.idle.start())
        close = QPushButton("✕", objectName="close")
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self.close_card)
        row.addWidget(self.input)
        row.addWidget(close)
        self.body.addLayout(row)
        self.idle = QTimer(self, singleShot=True, interval=self.IDLE_HIDE_MS)
        self.idle.timeout.connect(self.close_card)

    def popup(self, near):
        """near: QRect of the crab window. Sits just above his speech-bubble area."""
        self.adjustSize()
        screen = (self.screen() or self.window().screen()).availableGeometry()
        x = near.center().x() - self.width() // 2
        x = max(screen.left() + 8, min(x, screen.right() - self.width() - 8))
        self.move(x, max(screen.top() + 8, near.top() - self.height() + 10))
        self.input.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.idle.start()

    def _submit(self):
        text = self.input.text().strip()
        if not text:  # Enter on an empty box = close
            self.close_card()
            return
        self.input.clear()
        self.idle.start()
        self.sent.emit(text)

    def close_card(self):
        self.idle.stop()
        super().close_card()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_card()
        else:
            super().keyPressEvent(e)


class HistoryBox(Panel):
    """Right-click → Chat history: the whole conversation. Links open normally."""
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 440)
        self.messages = []      # (who, html) with who = "you" | "crab"
        self.typing = False

        header = QHBoxLayout()
        title = QLabel("🦀 Crab", objectName="title")
        self.status = QLabel()
        self.status.setStyleSheet("font-size: 10px; color: #8a5a50;")
        close = QPushButton("✕", objectName="close")
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self.close_card)
        header.addWidget(title)
        header.addWidget(self.status, 1)
        header.addWidget(close)
        self.body.addLayout(header)

        self.log = QTextBrowser(openLinks=False)
        self.log.anchorClicked.connect(QDesktopServices.openUrl)
        self.log.setStyleSheet(
            "QTextBrowser { background: white; border: 2px solid #3a1014; border-radius: 6px;"
            f" font-family: {MONO}; font-size: 12px; color: #3a1014; }}"
        )
        self.body.addWidget(self.log, 1)

    def set_status(self, text):
        self.status.setText(text)

    def add(self, who, html):
        self.messages.append((who, html))
        self.typing = False
        self._render()

    def set_typing(self, typing):
        self.typing = typing
        self._render()

    def _render(self):
        rows = []
        shown = self.messages + ([("crab", "<i>…</i>")] if self.typing else [])
        for who, html in shown:
            align, color = ("right", "#ffd9c7") if who == "you" else ("left", "#f3ece2")
            rows.append(
                f'<table width="100%" cellspacing="0"><tr><td align="{align}">'
                f'<table bgcolor="{color}" cellpadding="7" cellspacing="0"><tr><td>{html}</td></tr></table>'
                "</td></tr></table>"
            )
        self.log.setHtml('<div style="margin: 2px">' + '<p style="margin: 3px"></p>'.join(rows) + "</div>")
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def popup(self, near):
        """near: QRect of the crab window. Open just above him, kept on-screen."""
        screen = (self.screen() or self.window().screen()).availableGeometry()
        x = near.center().x() - self.width() // 2
        y = near.bottom() - 150 - self.height()
        x = max(screen.left() + 8, min(x, screen.right() - self.width() - 8))
        self.move(x, max(screen.top() + 8, y))
        self.show()
        self.raise_()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_card()
        else:
            super().keyPressEvent(e)


class FileList(QListWidget):
    """List whose rows can be dragged out as real files (to Desktop, email, etc.)."""

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setIconSize(QSize(44, 44))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.ElideMiddle)

    def mimeData(self, items):
        data = QMimeData()
        data.setUrls([item_url(i.data(Qt.UserRole)) for i in items])
        return data


class ResultCard(Panel):
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(420)
        self.icons = QFileIconProvider()
        self.previews = {}

        header = QHBoxLayout()
        self.title = QLabel(objectName="title")
        close = QPushButton("✕", objectName="close")
        close.clicked.connect(self.close_card)
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(close)
        self.body.addLayout(header)

        # Big preview of whichever file is selected.
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setFixedHeight(PREVIEW_H)
        self.preview.setStyleSheet("background: white; border: 2px solid #3a1014; border-radius: 6px;")
        self.body.addWidget(self.preview)
        self.path_label = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        self.path_label.setStyleSheet("font-size: 11px;")
        self.body.addWidget(self.path_label)

        self.list = FileList()
        self.list.currentItemChanged.connect(self._show_selected)
        self.list.itemDoubleClicked.connect(lambda item: open_file(item.data(Qt.UserRole).path))
        self.body.addWidget(self.list)

        hint = QLabel("Double-click to open · drag a file out to copy it")
        hint.setStyleSheet("font-size: 10px; color: #8a5a50;")
        self.body.addWidget(hint)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda: self.selected() and open_file(self.selected().path))
        show_btn = QPushButton("Show in folder")
        show_btn.clicked.connect(lambda: self.selected() and reveal_in_folder(self.selected().path))
        buttons.addWidget(open_btn)
        buttons.addWidget(show_btn)
        buttons.addStretch()
        self.body.addLayout(buttons)

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def big_picture(self, hit):
        """The file's preview if it has one, otherwise its system icon, large."""
        pix = self.previews.get(hit.path)
        if pix is None:
            pix = self.icons.icon(QFileInfo(str(hit.path))).pixmap(128, 128)
        return pix.scaled(PREVIEW_H - 12, PREVIEW_H - 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _show_selected(self, item, _previous=None):
        if item is None:
            return
        hit = item.data(Qt.UserRole)
        self.preview.setPixmap(self.big_picture(hit))
        self.path_label.setText(f"<b>{escape(hit.path.name)}</b> · {hit.size_text}<br>{escape(hit.folder)}")

    def show_hits(self, hits, previews, near):
        """previews: {path: QPixmap}. near: QRect of the crab window; the card goes beside it."""
        self.previews = previews
        self.title.setText("Found it!" if len(hits) == 1 else f"Found {len(hits)} matches")
        self.list.clear()
        for hit in hits:
            when = datetime.fromtimestamp(hit.mtime).strftime("%b %d, %Y")
            item = QListWidgetItem(f"{hit.path.name}\n{hit.size_text} · {when}")
            icon = previews.get(hit.path)
            item.setIcon(QIcon(icon) if icon else self.icons.icon(QFileInfo(str(hit.path))))
            item.setData(Qt.UserRole, hit)
            item.setToolTip(str(hit.path))
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.setFixedHeight(min(5, len(hits)) * 56 + 8)
        self.show_beside(near)


class WebCard(Panel):
    """Web search results: title, site, snippet. Double-click or Open to visit."""
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(480)
        self.query = ""

        header = QHBoxLayout()
        self.title = QLabel(objectName="title")
        close = QPushButton("✕", objectName="close")
        close.clicked.connect(self.close_card)
        header.addWidget(self.title, 1)
        header.addWidget(close)
        self.body.addLayout(header)

        self.list = FileList()
        self.list.setIconSize(QSize(0, 0))
        self.list.itemDoubleClicked.connect(lambda item: QDesktopServices.openUrl(item_url(item.data(Qt.UserRole))))
        self.body.addWidget(self.list)

        hint = QLabel("Double-click to open · results from DuckDuckGo")
        hint.setStyleSheet("font-size: 10px; color: #8a5a50;")
        self.body.addWidget(hint)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self._open_selected)
        more_btn = QPushButton("See all in browser")
        more_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(browser_url(self.query))))
        buttons.addWidget(open_btn)
        buttons.addWidget(more_btn)
        buttons.addStretch()
        self.body.addLayout(buttons)

    def _open_selected(self):
        item = self.list.currentItem()
        if item:
            QDesktopServices.openUrl(item_url(item.data(Qt.UserRole)))

    def show_hits(self, query, hits, near):
        self.query = query
        self.title.setText(f"🌐 {query}")
        self.list.clear()
        height = 8
        for hit in hits:
            snippet = hit.snippet if len(hit.snippet) < 140 else hit.snippet[:137] + "…"
            row = QLabel(
                f"<b>{escape(hit.title)}</b><br>"
                f"<span style='color:#2a7a3a'>{escape(hit.domain)}</span><br>"
                f"<span style='color:#6a4a44'>{escape(snippet)}</span>",
                wordWrap=True,
            )
            row.setContentsMargins(6, 5, 6, 5)
            width = self.width() - 60
            row.setFixedWidth(width)
            row.setParent(self.list.viewport())  # inherit the stylesheet font before measuring
            row.ensurePolished()
            row.setFixedHeight(row.heightForWidth(width) + 6)  # wrapped text needs its real height
            row.setAttribute(Qt.WA_TransparentForMouseEvents)  # clicks go to the list row
            item = QListWidgetItem()
            item.setData(Qt.UserRole, hit)
            item.setToolTip(hit.url)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            height += row.sizeHint().height()
        self.list.setCurrentRow(0)
        self.list.setFixedHeight(min(height, 420))
        self.show_beside(near)
