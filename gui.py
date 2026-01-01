# gui.py
from __future__ import annotations
import json
import os
import threading
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, Qt, QUrl, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QTabWidget, QTabBar,
    QMessageBox, QCheckBox, QSplitter
)
from PyQt6.QtGui import QTextCursor, QKeySequence, QDesktopServices, QKeyEvent, QShortcut
from PyQt6.QtQuickWidgets import QQuickWidget

from amazon import scrape_amazon
from bulk_parser import parse_bulk_items
from ebay import list_on_ebay
from tokens import load_tokens, get_application_token, save_tokens, get_ebay_user_token, clear_user_token
from ui_bridge import IOBridge


class GUIIOBridge(IOBridge, QObject):
    log_signal = pyqtSignal(str)
    open_url_signal = pyqtSignal(str)
    _prompt_text_signal = pyqtSignal(str, str, int)
    _prompt_choice_signal = pyqtSignal(str, list, int)

    def __init__(self, parent: QWidget):
        QObject.__init__(self)
        self.parent = parent
        self._pending: Dict[int, Tuple[threading.Event, Optional[str]]] = {}
        self._counter = 0

        self.log_signal.connect(self._on_log)
        self.open_url_signal.connect(self._on_open_url)
        self._prompt_text_signal.connect(self._on_prompt_text)
        self._prompt_choice_signal.connect(self._on_prompt_choice)

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    # IOBridge API
    def log(self, msg: str) -> None:
        self.log_signal.emit(str(msg))

    def prompt_text(self, prompt: str, default: str = "") -> str:
        rid = self._next_id()
        ev = threading.Event()
        self._pending[rid] = (ev, None)
        self._prompt_text_signal.emit(prompt, default, rid)
        ev.wait()
        _, val = self._pending.pop(rid, (None, default))
        return val if val is not None else default

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        rid = self._next_id()
        ev = threading.Event()
        self._pending[rid] = (ev, None)
        self._prompt_choice_signal.emit(prompt, options, rid)
        ev.wait()
        _, val = self._pending.pop(rid, (None, None))
        return val

    def open_url(self, url: str) -> None:
        self.open_url_signal.emit(url)

    # Slots
    def _on_log(self, msg: str):
        if hasattr(self.parent, 'append_log'):
            self.parent.append_log(msg)

    def _on_open_url(self, url: str):
        # Load URLs in a new embedded browser tab
        if hasattr(self.parent, 'load_in_browser'):
            self.parent.load_in_browser(url, new_tab=True)
        else:
            try:
                QDesktopServices.openUrl(QUrl(url))
            except Exception:
                pass

    def resolve_prompt(self, rid: int, value):
        ev, _ = self._pending.get(rid, (None, None))
        if ev:
            self._pending[rid] = (ev, value)
            ev.set()

    def _on_prompt_text(self, prompt: str, default: str, rid: int):
        # Delegate to inline prompt in main window
        if hasattr(self.parent, 'show_text_prompt'):
            self.parent.show_text_prompt(prompt, default, rid)
        else:
            # Fallback minimal
            self.resolve_prompt(rid, default)

    def _on_prompt_choice(self, prompt: str, options: List[str], rid: int):
        # Delegate to inline prompt in main window
        if hasattr(self.parent, 'show_choice_prompt'):
            self.parent.show_choice_prompt(prompt, options, rid)
        else:
            self.resolve_prompt(rid, options[0] if options else None)


# Remove BrowserView (QWebEngine) and replace with a WebView2Tab using QML WebView
class WebView2Tab(QWidget):
    def __init__(self, main_ref, initial_url: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._can_back = False
        self._can_fwd = False

        self._main = main_ref
        self._last_title = ""
        self._last_url = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.quick = QQuickWidget(self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        # Prepare persistent profile path and expose to QML context BEFORE loading the scene
        profile_dir = os.path.abspath(os.path.join(os.getcwd(), 'web_profile'))
        try:
            os.makedirs(profile_dir, exist_ok=True)
        except Exception:
            pass
        try:
            norm_profile_dir = profile_dir.replace('\\', '/')
            self.quick.rootContext().setContextProperty("webProfilePath",
                                                        norm_profile_dir)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Load QML scene
        qml_path = os.path.abspath(os.path.join(os.getcwd(), 'webview.qml'))
        self.quick.setSource(QUrl.fromLocalFile(qml_path))
        lay.addWidget(self.quick)
        root = self.quick.rootObject()

        # Connect QML signals to update tab title/address and open new tabs
        try:
            root.titleChangedPy.connect(self._on_title_changed)  # type: ignore[attr-defined]
            root.urlChangedPy.connect(self._on_url_changed)  # type: ignore[attr-defined]
            root.newWindowRequestedPy.connect(self._on_new_window)  # type: ignore[attr-defined]
            root.canNavigateChangedPy.connect(self._on_can_nav_changed)  # type: ignore[attr-defined]
        except Exception:
            pass

        if initial_url:
            try:
                # Set and load the initial URL
                root.setProperty('initialUrl', initial_url)
                if hasattr(root, 'loadUrl'):
                    root.loadUrl(initial_url)  # type: ignore[call-arg]
            except Exception:
                pass

    def _on_can_nav_changed(self, can_back: bool, can_fwd: bool):
        self._can_back = bool(can_back)
        self._can_fwd = bool(can_fwd)
        try:
            self._main._refresh_nav(self)
        except Exception:
            pass

    # QML signal handlers
    def _on_title_changed(self, title: str):
        self._last_title = title or ""
        try:
            self._main._update_tab_title(self)
        except Exception:
            pass

    def _on_url_changed(self, url_str: str):
        self._last_url = url_str or ""
        try:
            self._main._on_view_url_changed(self, QUrl(self._last_url))
        except Exception:
            pass

    def _on_new_window(self, url_str: str):
        try:
            self._main.create_browser_tab(url_str)
        except Exception:
            pass

    # API used by MainWindow
    def title(self) -> str:
        return self._last_title

    def url(self) -> QUrl:
        try:
            return QUrl(self._last_url)
        except Exception:
            return QUrl()

    def setUrl(self, url: QUrl | str):
        try:
            root = self.quick.rootObject()
            if isinstance(url, QUrl):
                url = url.toString()
            if hasattr(root, 'loadUrl'):
                root.loadUrl(url)  # type: ignore[call-arg]
        except Exception:
            pass

    def back(self):
        try:
            root = self.quick.rootObject()
            if hasattr(root, 'goBack'):
                root.goBack()
        except Exception:
            pass

    def forward(self):
        try:
            root = self.quick.rootObject()
            if hasattr(root, 'goForward'):
                root.goForward()
        except Exception:
            pass

    def reload(self):
        try:
            root = self.quick.rootObject()
            if hasattr(root, 'reload'):
                root.reload()
        except Exception:
            pass

    def canGoBack(self) -> bool:
        return self._can_back

    def canGoForward(self) -> bool:
        return self._can_fwd


class MainWindow(QWidget):
    bulk_finished_signal = pyqtSignal()
    scrape_done = pyqtSignal(dict)
    list_done = pyqtSignal(dict)
    bulk_done = pyqtSignal(int)
    toggle_ui = pyqtSignal(bool)

    def _on_bulk_finished(self):
        """Cleans up UI after a bulk run. Runs in the GUI thread."""
        self._bulk_running = False
        self.bulk_process_btn.setEnabled(True)
        self.bulk_pause_btn.hide()
        self.bulk_cancel_btn.hide()

    def _refresh_nav(self, view: Optional[WebView2Tab] = None):
        """Enable/disable back/forward buttons based on the current view's history."""
        try:
            if view is None:
                view = self.browser_tabs.currentWidget()
            if isinstance(view, WebView2Tab):
                self.nav_back.setEnabled(view.canGoBack())
                self.nav_forward.setEnabled(view.canGoForward())
            else:
                self.nav_back.setEnabled(False)
                self.nav_forward.setEnabled(False)
        except Exception:
            self.nav_back.setEnabled(False)
            self.nav_forward.setEnabled(False)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Amazon → eBay Lister")
        self.resize(1200, 800)
        self.bridge = GUIIOBridge(self)
        self._product: Optional[Dict[str, Any]] = None
        # State for bulk processing
        self._bulk_running = False
        self._bulk_pause_event = threading.Event()
        self._bulk_cancel_event = threading.Event()
        # Keep references to running fade timers per widget
        self._fade_timers: Dict[QObject, object] = {}
        # Rightmost "+" tab placeholder
        self._plus_tab_widget: Optional[QWidget] = None
        # Default URL for any new tab
        self._new_tab_url: str = os.getenv("DEFAULT_NEW_TAB_URL", "https://www.google.com")

        # Root split layout: left controls, right browser
        root_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout.addWidget(splitter)

        # Left pane container
        left_pane = QWidget(self)
        left_layout = QVBoxLayout(left_pane)

        # Tabs
        self.tabs = QTabWidget(left_pane)
        left_layout.addWidget(self.tabs)

        # Single tab
        self.single_tab = QWidget(self)
        self.tabs.addTab(self.single_tab, "Single")
        s_layout = QVBoxLayout(self.single_tab)

        # Inputs (left side)
        form = QHBoxLayout()
        s_layout.addLayout(form)
        form.addWidget(QLabel("Amazon URL:"))
        self.url_edit = QLineEdit(self)
        form.addWidget(self.url_edit)
        self.load_btn = QPushButton("Load from JSON…", self)
        form.addWidget(self.load_btn)

        form2 = QHBoxLayout()
        s_layout.addLayout(form2)
        form2.addWidget(QLabel("Quantity:"))
        self.qty_edit = QLineEdit(self)
        self.qty_edit.setPlaceholderText("1")
        self.qty_edit.setFixedWidth(80)
        form2.addWidget(self.qty_edit)
        form2.addWidget(QLabel("Private Note:"))
        self.note_edit = QLineEdit(self)
        form2.addWidget(self.note_edit)

        self.custom_specs = QLineEdit(self)
        self.custom_specs.setPlaceholderText("Custom specifics e.g. Size: XL | Colour: Black")
        s_layout.addWidget(self.custom_specs)

        btn_row = QHBoxLayout()
        s_layout.addLayout(btn_row)
        self.auth_btn = QPushButton("Authorize eBay / Refresh Tokens", self)
        btn_row.addWidget(self.auth_btn)
        # New: Logout button
        self.logout_btn = QPushButton("Logout eBay", self)
        btn_row.addWidget(self.logout_btn)
        self.scrape_btn = QPushButton("Scrape Amazon", self)
        btn_row.addWidget(self.scrape_btn)
        self.list_btn = QPushButton("List on eBay", self)
        self.list_btn.setEnabled(False)
        btn_row.addWidget(self.list_btn)

        # Bulk tab (left side)
        self.bulk_tab = QWidget(self)
        self.tabs.addTab(self.bulk_tab, "Bulk")
        b_layout = QVBoxLayout(self.bulk_tab)
        self.bulk_text = QTextEdit(self)
        self.bulk_text.setPlaceholderText(
            "Paste bulk text here. Example:\nhttps://www.amazon.co.uk/…\nQuantity: 2\nNote: Gift\nSize: L | Colour: Red\n\n…")
        b_layout.addWidget(self.bulk_text)
        b_row = QHBoxLayout()
        b_layout.addLayout(b_row)
        self.bulk_process_btn = QPushButton("Process Bulk", self)
        b_row.addWidget(self.bulk_process_btn)
        self.bulk_pause_btn = QPushButton("Pause", self)
        self.bulk_pause_btn.hide()
        b_row.addWidget(self.bulk_pause_btn)
        self.bulk_cancel_btn = QPushButton("Cancel", self)
        self.bulk_cancel_btn.hide()
        b_row.addWidget(self.bulk_cancel_btn)
        b_row.addStretch(1)

        # Inline prompt panel (left side)
        self.prompt_panel = QWidget(self)
        pp_layout = QHBoxLayout(self.prompt_panel)
        self.prompt_label = QLabel("", self.prompt_panel)
        # Assign a stable object name for targeted styling (optional)
        self.prompt_label.setObjectName("prompt_label")
        pp_layout.addWidget(self.prompt_label)
        self.prompt_edit = QLineEdit(self.prompt_panel)
        pp_layout.addWidget(self.prompt_edit)
        from PyQt6.QtWidgets import QComboBox
        self.prompt_combo = QComboBox(self.prompt_panel)
        pp_layout.addWidget(self.prompt_combo)
        self.prompt_ok = QPushButton("OK", self.prompt_panel)
        self.prompt_cancel = QPushButton("Cancel", self.prompt_panel)
        pp_layout.addWidget(self.prompt_ok)
        pp_layout.addWidget(self.prompt_cancel)
        self.prompt_panel.hide()
        left_layout.addWidget(self.prompt_panel)

        # Log area (left side)
        self.toggle_log_btn = QPushButton("Show Log", self)
        left_layout.addWidget(self.toggle_log_btn)
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.hide()
        left_layout.addWidget(self.log_view)

        # Right pane container with URL bar + tabs
        right_container = QWidget(self)
        right_layout = QVBoxLayout(right_container)

        # URL bar
        url_row = QHBoxLayout()
        # Navigation buttons
        self.nav_back = QPushButton("◀", right_container)
        self.nav_forward = QPushButton("▶", right_container)
        self.nav_refresh = QPushButton("⟳", right_container)
        self.nav_back.setEnabled(False)
        self.nav_forward.setEnabled(False)

        url_row.addWidget(self.nav_back)
        url_row.addWidget(self.nav_forward)
        url_row.addWidget(self.nav_refresh)
        self.addr_bar = QLineEdit(right_container)
        self.addr_bar.setPlaceholderText("Enter URL and press Enter…")
        self.addr_go = QPushButton("Go", right_container)
        # New: Open current address in Microsoft Edge (WebView2 runtime)
        self.addr_open_edge = QPushButton("Edge", right_container)
        # New: Toggle to use Edge (WebView2) for all browsing actions
        self.edge_mode_cb = QCheckBox("Edge mode", right_container)
        url_row.addWidget(self.addr_bar)
        url_row.addWidget(self.addr_go)
        url_row.addWidget(self.addr_open_edge)
        url_row.addWidget(self.edge_mode_cb)
        right_layout.addLayout(url_row)

        # Browser tabs
        self.browser_tabs = QTabWidget(self)
        self.browser_tabs.setTabsClosable(True)
        self.browser_tabs.tabCloseRequested.connect(self.on_close_tab)
        right_layout.addWidget(self.browser_tabs)

        # Add "+" rightmost tab and first content tab
        self._setup_plus_tab()
        self.create_browser_tab(self._new_tab_url)

        # Replace previous add of browser_tabs with right_container
        splitter.addWidget(left_pane)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # Connections
        self.bulk_finished_signal.connect(self._on_bulk_finished)
        self.toggle_log_btn.clicked.connect(self.on_toggle_log)
        self.load_btn.clicked.connect(self.on_load_json)
        self.auth_btn.clicked.connect(self.on_auth)
        # New: logout handler
        self.logout_btn.clicked.connect(self.on_logout)
        self.scrape_btn.clicked.connect(self.on_scrape)
        self.list_btn.clicked.connect(self.on_list)
        self.bulk_process_btn.clicked.connect(self.on_process_bulk)
        self.bulk_pause_btn.clicked.connect(self.on_bulk_pause_resume)
        self.bulk_cancel_btn.clicked.connect(self.on_bulk_cancel)
        self.addr_go.clicked.connect(self.on_addr_enter)
        self.addr_bar.returnPressed.connect(self.on_addr_enter)
        self.browser_tabs.currentChanged.connect(self.on_tab_changed)
        # Create a new tab only when the '+' tab is explicitly clicked
        try:
            self.browser_tabs.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)
        except Exception:
            pass
        self.nav_back.clicked.connect(self.on_back)
        self.nav_forward.clicked.connect(self.on_forward)
        self.nav_refresh.clicked.connect(self.on_reload)
        # New: open current URL in Microsoft Edge (WebView2-based browser)
        self.addr_open_edge.clicked.connect(self.on_open_in_edge)
        self.edge_mode_cb.toggled.connect(
            lambda _: self.bridge.log("Edge mode: ON" if self.edge_mode_cb.isChecked() else "Edge mode: OFF"))

        # Keyboard shortcuts
        self._shortcuts: List[QShortcut] = []
        self._add_shortcut("Ctrl+Tab", lambda: self._switch_tab(1))
        self._add_shortcut("Ctrl+Shift+Tab", lambda: self._switch_tab(-1))
        self._add_shortcut("F5", self.on_reload)
        self._add_shortcut("Ctrl+R", self.on_reload)
        self._add_shortcut("Alt+Left", self.on_back)
        self._add_shortcut("Alt+Right", self.on_forward)
        # New: Ctrl+T opens a new tab with default URL
        self._add_shortcut("Ctrl+T", lambda: self.create_browser_tab(self._new_tab_url))
        # New: Ctrl+W closes the current tab (respects last-tab protection)
        self._add_shortcut("Ctrl+W", self.on_close_current_tab)

        # Signal handlers (GUI thread)
        self.scrape_done.connect(self._on_scrape_done)
        self.list_done.connect(self._on_list_done)
        self.bulk_done.connect(lambda n: QMessageBox.information(self, "Bulk Done", f"Processed {n} items."))
        self.toggle_ui.connect(self.set_processing)

        # Prompt buttons
        self.prompt_ok.clicked.connect(self._on_prompt_ok)
        self.prompt_cancel.clicked.connect(self._on_prompt_cancel)
        self._active_prompt = {"rid": None, "mode": None, "default": None}

        # Global mouse back/forward handling
        # Global mouse/keyboard back/forward handling (works even inside the web view)
        QApplication.instance().installEventFilter(self)

    def _setup_plus_tab(self):
        try:
            if self._plus_tab_widget and self.browser_tabs.indexOf(self._plus_tab_widget) != -1:
                return
        except Exception:
            pass
        w = QWidget(self)
        w.setObjectName("plus_tab")
        self._plus_tab_widget = w
        # Always keep this as the last tab
        self.browser_tabs.addTab(w, "+")
        try:
            idx = self.browser_tabs.indexOf(w)
            self.browser_tabs.setTabToolTip(idx, "New tab")
            # Hide the close button specifically for the '+' tab
            tb = self.browser_tabs.tabBar()
            tb.setTabButton(idx, QTabBar.ButtonPosition.RightSide, None)
            tb.setTabButton(idx, QTabBar.ButtonPosition.LeftSide, None)
        except Exception:
            pass

    # Browser helpers
    def create_browser_tab(self, url: Optional[str] = None) -> WebView2Tab:
        view = WebView2Tab(self, url or self._new_tab_url, self.browser_tabs)
        try:
            plus_idx = self.browser_tabs.indexOf(self._plus_tab_widget) if self._plus_tab_widget else -1
        except Exception:
            plus_idx = -1
        if plus_idx is not None and plus_idx >= 0:
            idx = self.browser_tabs.insertTab(plus_idx, view, "Tab")
        else:
            idx = self.browser_tabs.addTab(view, "Tab")
        self.browser_tabs.setCurrentIndex(idx)
        # Initial refresh
        self._refresh_nav(view)
        return view

    def _on_view_url_changed(self, view: WebView2Tab, url):
        self._update_tab_title(view)
        if self.browser_tabs.currentWidget() is view:
            try:
                self.addr_bar.setText(url.toString())
            except Exception:
                pass
            self._refresh_nav(view)

    def _update_tab_title(self, view: WebView2Tab):
        idx = self.browser_tabs.indexOf(view)
        if idx != -1:
            title = view.title() or view.url().toString()
            if title:
                self.browser_tabs.setTabText(idx, title[:24])

    def on_close_tab(self, index: int):
        """Close a content tab safely, switch focus to a neighbor, and never
        allow closing the last remaining content tab (excludes the '+' tab)."""
        try:
            total = self.browser_tabs.count()
            # Count actual content tabs (BrowserView), independent of '+' presence
            content_count = 0
            for i in range(total):
                try:
                    if isinstance(self.browser_tabs.widget(i), WebView2Tab):
                        content_count += 1
                except Exception:
                    pass
            # Don't allow closing the last remaining content tab
            if content_count <= 1:
                return

            # Pick a sensible next tab to focus (prefer right neighbor, else left), must be a BrowserView
            next_widget = None
            try:
                if index + 1 < total:
                    w_right = self.browser_tabs.widget(index + 1)
                    if isinstance(w_right, WebView2Tab):
                        next_widget = w_right
            except Exception:
                pass
            if next_widget is None:
                try:
                    if index - 1 >= 0:
                        w_left = self.browser_tabs.widget(index - 1)
                        if isinstance(w_left, WebView2Tab):
                            next_widget = w_left
                except Exception:
                    pass

            # Remove the tab and delete its widget
            w = self.browser_tabs.widget(index)
            self.browser_tabs.removeTab(index)
            try:
                if w:
                    w.deleteLater()
            except Exception:
                pass

            # Ensure '+' tab placement
            self._setup_plus_tab()

            # Focus the chosen next tab if available; otherwise first content tab
            try:
                if next_widget is not None:
                    new_idx = self.browser_tabs.indexOf(next_widget)
                    if new_idx != -1:
                        self.browser_tabs.setCurrentIndex(new_idx)
                else:
                    total2 = self.browser_tabs.count()
                    for i in range(total2):
                        w2 = self.browser_tabs.widget(i)
                        if isinstance(w2, WebView2Tab):
                            self.browser_tabs.setCurrentIndex(i)
                            break
            except Exception:
                pass

            # Refresh address/nav to reflect new active tab
            try:
                self.on_tab_changed(self.browser_tabs.currentIndex())
            except Exception:
                pass
        except Exception:
            pass

    def on_tab_changed(self, index: int):
        """Update address/nav when the active tab changes. If '+' becomes active,
        don't auto-open anything; just clear the UI until user opens a tab."""
        try:
            if self._plus_tab_widget and index == self.browser_tabs.indexOf(self._plus_tab_widget):
                try:
                    self.addr_bar.clear()
                except Exception:
                    pass
                self._refresh_nav(None)
                return
        except Exception:
            pass
        view = self.browser_tabs.widget(index)
        if isinstance(view, WebView2Tab):
            try:
                self.addr_bar.setText(view.url().toString())
            except Exception:
                self.addr_bar.clear()
            self._refresh_nav(view)
        else:
            self.addr_bar.clear()
            self._refresh_nav(None)

    def _on_tab_bar_clicked(self, index: int):
        """Handle clicks on the tab bar; create a new tab if '+' was clicked."""
        try:
            tb = self.browser_tabs.tabBar()
            # Match either the '+' widget index or the '+' label to be robust
            is_plus_index = False
            try:
                if self._plus_tab_widget and index == self.browser_tabs.indexOf(self._plus_tab_widget):
                    is_plus_index = True
            except Exception:
                pass
            is_plus_label = False
            try:
                is_plus_label = (tb.tabText(index).strip() == "+")
            except Exception:
                pass
            if is_plus_index or is_plus_label:
                self.create_browser_tab(self._new_tab_url)
        except Exception:
            pass

    def load_in_browser(self, url: str, new_tab: bool = False):
        try:
            # If Edge mode is enabled, always open externally in Edge
            if getattr(self, 'edge_mode_cb', None) and self.edge_mode_cb.isChecked():
                self._open_url_in_edge(url)
                return
            if new_tab or self.browser_tabs.count() == 0:
                self.create_browser_tab(url)
            else:
                self.navigate_current(url)
        except Exception:
            pass

    def on_addr_enter(self):
        text = (self.addr_bar.text() or "").strip()
        if not text:
            return
        # If looks like a URL with scheme, navigate directly
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', text):
            if getattr(self, 'edge_mode_cb', None) and self.edge_mode_cb.isChecked():
                self._open_url_in_edge(text)
            else:
                self.navigate_current(text)
            return
        # If looks like a plausible domain/path with no spaces, prepend https://
        if re.match(r'^[^\s/:]+\.[^\s/:]+.*$', text):
            url = "https://" + text
            if getattr(self, 'edge_mode_cb', None) and self.edge_mode_cb.isChecked():
                self._open_url_in_edge(url)
            else:
                self.navigate_current(url)
            return
        # Otherwise, run a Google search
        q = urllib.parse.quote_plus(text)
        url = f"https://www.google.com/search?q={q}"
        if getattr(self, 'edge_mode_cb', None) and self.edge_mode_cb.isChecked():
            self._open_url_in_edge(url)
        else:
            self.navigate_current(url)

    def _open_url_in_edge(self, url: str):
        try:
            # Normalize to absolute URL
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url):
                if re.match(r'^[^\s/:]+\.[^\s/:]+.*$', url):
                    url = "https://" + url
                else:
                    q = urllib.parse.quote_plus(url)
                    url = f"https://www.google.com/search?q={q}"
            edge_url = QUrl(f"microsoft-edge:{url}")
            QDesktopServices.openUrl(edge_url)
        except Exception:
            try:
                QDesktopServices.openUrl(QUrl(url))
            except Exception:
                pass

    def on_open_in_edge(self):
        """Open current address in Microsoft Edge (uses WebView2 runtime under the hood)."""
        url = ""
        try:
            url = (self.addr_bar.text() or "").strip()
            if not url:
                # try to get from current tab
                try:
                    view = self.browser_tabs.currentWidget()
                    if isinstance(view, WebView2Tab):
                        url = view.url().toString()
                except Exception:
                    pass
            if not url:
                return
            self._open_url_in_edge(url)
        except Exception:
            # As a fallback, open normally with default browser
            try:
                if url:
                    QDesktopServices.openUrl(QUrl(url))
            except Exception:
                pass

    def navigate_current(self, url: str):
        try:
            if self.browser_tabs.count() == 0:
                self.create_browser_tab(url)
                return
            view = self.browser_tabs.currentWidget()
            if not isinstance(view, WebView2Tab):
                # If '+' tab or any non-browser tab is active, open a new browser tab
                self.create_browser_tab(url)
                return
            view.setUrl(url)
        except Exception:
            pass

    # Inline prompts
    def show_text_prompt(self, prompt: str, default: str, rid: int):
        self._active_prompt = {"rid": rid, "mode": "text", "default": default}
        self.prompt_label.setText(prompt)
        self.prompt_edit.setText(default)
        self.prompt_edit.show()
        self.prompt_combo.hide()
        self.prompt_panel.show()
        self.prompt_edit.setFocus()
        # Briefly highlight the question so it's easy to notice
        try:
            self._highlight_then_fade(self.prompt_label)
        except Exception:
            pass

    def show_choice_prompt(self, prompt: str, options: List[str], rid: int):
        self._active_prompt = {"rid": rid, "mode": "choice", "default": None}
        self.prompt_label.setText(prompt)
        self.prompt_combo.clear()
        self.prompt_combo.addItems(options)
        self.prompt_combo.show()
        self.prompt_edit.hide()
        self.prompt_panel.show()
        self.prompt_combo.setFocus()
        # Briefly highlight the question so it's easy to notice
        try:
            self._highlight_then_fade(self.prompt_label)
        except Exception:
            pass

    def _highlight_then_fade(self, widget: QWidget, rgb: Tuple[int, int, int] = (255, 246, 173),
                             duration_ms: int = 1500, steps: int = 12):
        """Set a temporary background highlight that fades away smoothly.
        Args:
            widget: The widget to highlight (e.g., the prompt label).
            rgb: Highlight base color.
            duration_ms: Total fade duration in milliseconds.
            steps: Number of fade steps.
        """
        try:
            from PyQt6.QtCore import QTimer
        except Exception:
            return
        # Cancel any existing fade on this widget
        old_timer = self._fade_timers.pop(widget, None)
        try:
            if old_timer:
                old_timer.stop()
        except Exception:
            pass
        # Ensure background is drawn
        try:
            widget.setAutoFillBackground(True)
        except Exception:
            pass
        r, g, b = rgb
        max_alpha = 210  # out of 255
        interval = max(15, int(duration_ms / max(1, steps)))
        state = {"step": 0}

        def apply(alpha: int):
            try:
                widget.setStyleSheet(f"background-color: rgba({r}, {g}, {b}, {alpha});")
            except Exception:
                pass

        apply(max_alpha)
        timer = QTimer(self)
        timer.setInterval(interval)

        def on_tick():
            try:
                state["step"] += 1
                remaining = steps - state["step"]
                if remaining <= 0:
                    timer.stop()
                    try:
                        widget.setStyleSheet("")
                    except Exception:
                        pass
                    self._fade_timers.pop(widget, None)
                    return
                alpha = int(max_alpha * remaining / steps)
                apply(max(0, min(255, alpha)))
            except Exception:
                try:
                    timer.stop()
                except Exception:
                    pass
                try:
                    widget.setStyleSheet("")
                except Exception:
                    pass
                self._fade_timers.pop(widget, None)

        timer.timeout.connect(on_tick)
        self._fade_timers[widget] = timer
        timer.start()

    def _on_prompt_ok(self):
        rid = self._active_prompt.get("rid")
        mode = self._active_prompt.get("mode")
        if rid is None:
            self.prompt_panel.hide()
            return
        if mode == "text":
            val = self.prompt_edit.text()
        else:
            val = self.prompt_combo.currentText()
        self.bridge.resolve_prompt(rid, val)
        self.prompt_panel.hide()

    def _on_prompt_cancel(self):
        rid = self._active_prompt.get("rid")
        default = self._active_prompt.get("default")
        if rid is not None:
            self.bridge.resolve_prompt(rid, default)
        self.prompt_panel.hide()

    # Logging helper
    def append_log(self, msg: str):
        self.log_view.append(msg)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    # UI actions
    def on_toggle_log(self):
        if self.log_view.isVisible():
            self.log_view.hide()
            self.toggle_log_btn.setText("Show Log")
        else:
            self.log_view.show()
            self.toggle_log_btn.setText("Hide Log")

    def on_load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Product JSON", os.getcwd(), "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._product = json.load(f)
            self.bridge.log(f"Loaded product from {path}")
            # Populate some fields for visibility
            self.url_edit.setText(self._product.get('URL', ''))
            if 'quantity' in self._product:
                self.qty_edit.setText(str(self._product['quantity']))
            if 'sellerNote' in self._product:
                self.note_edit.setText(self._product['sellerNote'])
            self.list_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load JSON: {e}")

    def on_auth(self):
        self.toggle_ui.emit(False)

        def work():
            try:
                tokens = load_tokens()
                app = get_application_token(tokens, self.bridge)
                if not app:
                    return
                tokens['application_token'] = app
                save_tokens(tokens, self.bridge)
                user = get_ebay_user_token(tokens, self.bridge)
                if not user:
                    return
                tokens['user_token'] = user
                save_tokens(tokens, self.bridge)
                self.bridge.log("All tokens are ready.")
            finally:
                self.toggle_ui.emit(True)

        threading.Thread(target=work, daemon=True).start()

    # New: Logout implementation
    def on_logout(self):
        # Confirm with the user
        try:
            reply = QMessageBox.question(
                self,
                "Logout from eBay",
                "This will remove the saved eBay user token (application token will be preserved). Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
        except Exception:
            reply = QMessageBox.StandardButton.Yes
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.toggle_ui.emit(False)

        def work():
            try:
                # Remove only the user token; keep the application token intact
                ok = clear_user_token(self.bridge)
                if ok:
                    self.bridge.log("User token cleared. Re-authorize to reconnect your eBay account.")
                else:
                    self.bridge.log("Failed to clear user token. Check permissions and try again.")
            finally:
                self.toggle_ui.emit(True)

        threading.Thread(target=work, daemon=True).start()

    def on_scrape(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter an Amazon URL.")
            return
        note = self.note_edit.text().strip()
        qty_txt = self.qty_edit.text().strip()
        qty = None
        if qty_txt:
            try:
                qty = int(qty_txt)
            except Exception:
                qty = None
        custom_specifics: Dict[str, str] = {}
        if self.custom_specs.text().strip():
            for part in self.custom_specs.text().split('|'):
                if ':' in part:
                    k, v = part.split(':', 1)
                    if k.strip() and v.strip():
                        custom_specifics[k.strip()] = v.strip()
        self.toggle_ui.emit(False)

        def work():
            try:
                product = scrape_amazon(url, note=note, quantity=qty, custom_specifics=custom_specifics, io=self.bridge)
                self.scrape_done.emit(product)
            finally:
                self.toggle_ui.emit(True)

        threading.Thread(target=work, daemon=True).start()

    def _on_scrape_done(self, product: Dict[str, Any]):
        self._product = product
        self.bridge.log("Product scraped. You can now list on eBay.")
        self.list_btn.setEnabled(True)
        try:
            with open('product.json', 'w', encoding='utf-8') as f:
                json.dump(product, f, indent=2)
        except Exception:
            pass

    def _ensure_ebay_auth(self) -> Optional[Dict[str, Any]]:
        """Ensure both application and user tokens are available and up-to-date.
        Returns the updated tokens dict on success, or None on failure.
        """
        try:
            tokens = load_tokens() or {}
            # Application token
            app = get_application_token(tokens, self.bridge)
            if not app:
                self.bridge.log("Failed to ensure application token.")
                return None
            tokens['application_token'] = app
            save_tokens(tokens, self.bridge)
            # User token (may trigger consent flow)
            user = get_ebay_user_token(tokens, self.bridge)
            if not user:
                self.bridge.log("Failed to ensure user token.")
                return None
            tokens['user_token'] = user
            save_tokens(tokens, self.bridge)
            return tokens
        except Exception as e:
            try:
                self.bridge.log(f"Auth ensure error: {e}")
            except Exception:
                pass
            return None

    def on_list(self):
        if not self._product:
            QMessageBox.warning(self, "No Product", "Please scrape or load a product first.")
            return
        self.toggle_ui.emit(False)

        def work():
            try:
                # Ensure eBay auth automatically before listing
                ensured = self._ensure_ebay_auth()
                if not ensured:
                    self.list_done.emit(
                        {"ok": False, "error": "Authentication failed. Check credentials and try again."})
                    return
                res = list_on_ebay(self._product, self.bridge)
                self.list_done.emit(res)
            finally:
                self.toggle_ui.emit(True)

        threading.Thread(target=work, daemon=True).start()

    def on_bulk_pause_resume(self):
        """Toggles the paused state of the bulk processing task."""
        if self._bulk_pause_event.is_set():  # is_set means it's running, so we pause it
            self._bulk_pause_event.clear()
            self.bulk_pause_btn.setText("Resume")
            self.bridge.log("Bulk processing paused.")
        else:  # it's paused, so we resume it
            self._bulk_pause_event.set()
            self.bulk_pause_btn.setText("Pause")
            self.bridge.log("Bulk processing resumed.")

    def on_bulk_cancel(self):
        """Requests cancellation of the bulk processing task."""
        reply = QMessageBox.question(
            self, "Cancel Bulk Process",
            "Are you sure you want to cancel the bulk process?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.bridge.log("Cancellation requested...")
            self._bulk_cancel_event.set()
            if not self._bulk_pause_event.is_set():
                self._bulk_pause_event.set()

    def _on_list_done(self, res: Dict[str, Any]):
        if res.get('ok'):
            QMessageBox.information(self, "Listing Complete", f"Success. Item ID: {res.get('item_id')}")
        else:
            QMessageBox.warning(self, "Listing Failed", f"Result: {res}")

    def on_process_bulk(self):
        text = self.bulk_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No Text", "Paste bulk text first.")
            return
        items = parse_bulk_items(text)
        if not items:
            QMessageBox.warning(self, "Parse Failed", "No items could be parsed from the text.")
            return

        self._bulk_running = True
        self.bulk_process_btn.setEnabled(False)
        self.bulk_pause_btn.setText("Pause")
        self.bulk_pause_btn.show()
        self.bulk_cancel_btn.show()

        def work():
            try:
                total_items = len(items)
                processed_count = 0
                self._bulk_pause_event.set()
                self._bulk_cancel_event.clear()

                ensured = self._ensure_ebay_auth()
                if not ensured:
                    QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Auth Failed",
                                                                      "Authentication failed. Check credentials and try again."))
                    return
                os.makedirs("bulk_products", exist_ok=True)

                for idx, item in enumerate(items, start=1):
                    self._bulk_pause_event.wait()  # This will block if paused
                    if self._bulk_cancel_event.is_set():
                        self.bridge.log("Bulk process cancelled.")
                        break

                    self.bridge.log(f"=== Processing Item {idx}/{total_items} ===")
                    # ... (The rest of the item processing logic is unchanged)
                    product = scrape_amazon(
                        item.get("url", ""),
                        note=item.get("note", ""),
                        quantity=item.get("quantity", 1),
                        custom_specifics=item.get("custom_specifics", {}),
                        io=self.bridge
                    )
                    if not product:
                        self.bridge.log(f"Skipping item {idx} due to scraping failure.")
                        continue

                    with open(os.path.join("bulk_products", f"product_{idx}.json"), 'w', encoding='utf-8') as f:
                        json.dump(product, f, indent=2)

                    res = list_on_ebay(product, self.bridge)
                    if res.get("ok"):
                        processed_count += 1

                if not self._bulk_cancel_event.is_set():
                    self.bridge.log(f"Bulk processing finished. Processed {processed_count} items.")
                    QTimer.singleShot(0, lambda: self.bulk_done.emit(processed_count))
            finally:
                self.bulk_finished_signal.emit()

        threading.Thread(target=work, daemon=True).start()

    def set_processing(self, enable: bool):
        try:
            if enable and getattr(self, '_bulk_running', False):
                return
            self.bulk_process_btn.setEnabled(enable)
        except Exception:
            pass

    def _add_shortcut(self, seq: str, handler):
        sc = QShortcut(QKeySequence(seq), self)
        sc.activated.connect(handler)
        self._shortcuts.append(sc)

    def _switch_tab(self, offset: int):
        try:
            count = self.browser_tabs.count()
            # Build list of indices for real content tabs (BrowserView), skipping '+'
            content_indices = []
            for i in range(count):
                try:
                    if isinstance(self.browser_tabs.widget(i), WebView2Tab):
                        content_indices.append(i)
                except Exception:
                    pass
            if len(content_indices) <= 1:
                # Nothing to cycle or only one content tab
                return
            cur_idx = self.browser_tabs.currentIndex()
            # Find position within content list; if currently on '+', choose edge based on direction
            try:
                cur_pos = content_indices.index(cur_idx)
            except ValueError:
                cur_pos = (-1 if offset > 0 else 0)
            # Normalize potentially large offsets
            step = 1 if offset >= 0 else -1
            new_pos = (cur_pos + step) % len(content_indices)
            self.browser_tabs.setCurrentIndex(content_indices[new_pos])
        except Exception:
            pass

    def on_back(self):
        view = self.browser_tabs.currentWidget()
        if isinstance(view, WebView2Tab) and view.canGoBack():
            try:
                view.back()
            finally:
                self._refresh_nav(view)

    def on_forward(self):
        view = self.browser_tabs.currentWidget()
        if isinstance(view, WebView2Tab) and view.canGoForward():
            try:
                view.forward()
            finally:
                self._refresh_nav(view)

    def on_reload(self):
        view = self.browser_tabs.currentWidget()
        if isinstance(view, WebView2Tab):
            try:
                view.reload()
            except Exception:
                pass

    def on_close_current_tab(self):
        """Close the currently selected browser tab, skipping the '+' tab and
        honoring the existing last-tab protection in on_close_tab."""
        try:
            idx = self.browser_tabs.currentIndex()
            if idx < 0:
                return
            w = self.browser_tabs.widget(idx)
            # Don't allow closing the '+' tab
            if getattr(self, '_plus_tab_widget', None) is not None and w is self._plus_tab_widget:
                return
            self.on_close_tab(idx)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            from PyQt6.QtCore import QEvent
            view = self.browser_tabs.currentWidget()
            # Mouse back/forward (extra buttons), anywhere in the app
            if event.type() == QEvent.Type.MouseButtonPress and isinstance(view, WebView2Tab):
                btn = event.button()
                mb = Qt.MouseButton
                back_btns = [getattr(mb, n) for n in ("BackButton", "XButton1", "ExtraButton1") if hasattr(mb, n)]
                fwd_btns = [getattr(mb, n) for n in ("ForwardButton", "XButton2", "ExtraButton2") if hasattr(mb, n)]
                if btn in back_btns:
                    try:
                        view.back()
                    except Exception:
                        pass
                    return True
                if btn in fwd_btns:
                    try:
                        view.forward()
                    except Exception:
                        pass
                    return True

            # Keyboard back/forward (Alt+Left/Right, dedicated Back/Forward keys)
            if event.type() == QEvent.Type.KeyPress and isinstance(view, WebView2Tab):
                ke: QKeyEvent = event  # type: ignore[assignment]
                key = ke.key()
                mods = ke.modifiers()
                if key in (Qt.Key.Key_Back, Qt.Key.Key_Backspace) and mods == Qt.KeyboardModifier.NoModifier:
                    if view.canGoBack():
                        view.back()
                        return True
                if key == Qt.Key.Key_Forward and mods == Qt.KeyboardModifier.NoModifier:
                    if view.canGoForward():
                        view.forward()
                        return True
                if (mods & Qt.KeyboardModifier.AltModifier) and key == Qt.Key.Key_Left:
                    if view.canGoBack():
                        view.back()
                        return True
                if (mods & Qt.KeyboardModifier.AltModifier) and key == Qt.Key.Key_Right:
                    if view.canGoForward():
                        view.forward()
                        return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


def run_gui():
    import sys
    # Force WebView backend to Edge WebView2 on Windows
    try:
        os.environ.setdefault('QTWEBVIEW_BACKEND', 'webview2')
    except Exception:
        pass
    # Prefer a bundled style by default; respect user override via QT_QUICK_CONTROLS_STYLE
    try:
        from PyQt6.QtQuickControls2 import QQuickStyle  # type: ignore
        style = os.environ.get('QT_QUICK_CONTROLS_STYLE', 'Fusion')
        os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', style)
        try:
            QQuickStyle.setStyle(style)
        except Exception:
            pass
    except Exception:
        pass
    # Ensure WebEngine (QML) is initialized and GL contexts are shared before creating the app
    try:
        from PyQt6.QtCore import QCoreApplication, Qt
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass
    try:
        from PyQt6 import QtWebEngineQuick  # noqa: F401
        # Some versions expose initialize(); call if present
        try:
            if hasattr(QtWebEngineQuick, 'initialize'):
                QtWebEngineQuick.initialize()
        except Exception:
            pass
    except Exception:
        pass
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
