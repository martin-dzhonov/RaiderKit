from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from common import (
    ACTIONS_PANEL_WIDTH,
    DETAILS_WIDTH,
    LOADOUTS_PANEL_WIDTH,
    MAX_WIDGET_SIZE,
    NORMAL_HEIGHT,
    TITLE_BAR_HEIGHT,
)


class OverlayUIMixin:

    def calculate_window_width(self, details=None):
        """Calculate the width using the currently visible panels."""

        if details is None:
            details = self.details_open

        panel_width = self.actions_panel_width + self.loadouts_panel_width
        panel_count = 2

        if details:
            panel_width += self.details_width
            panel_count += 1

        margins = 14 * 2
        spacing = 14 * (panel_count - 1)
        frame_margins = 2

        return panel_width + margins + spacing + frame_margins

    def _resize_window(self, width):
        """Resize the overlay without changing its mode."""

        self.setMinimumWidth(0)
        self.setMaximumWidth(MAX_WIDGET_SIZE)
        self.resize(width, self.normal_height)

        self.central_frame.updateGeometry()
        self.ui_stack.updateGeometry()
        self.updateGeometry()

        QTimer.singleShot(
            0,
            lambda target_width=width: self._apply_deferred_resize(target_width),
        )

    def _apply_deferred_resize(self, width):

        self.resize(width, self.normal_height)
        self.central_frame.updateGeometry()
        self.updateGeometry()

    def _build_main_panel(self):

        root = QWidget()
        root.setObjectName("mainPanel")

        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        self.status = QLabel("Loading assets...")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.status.hide()

        # ACTIONS PANEL

        self.actions_panel = QWidget()
        self.actions_panel.setObjectName("actionsPanel")
        self.actions_panel.setFixedWidth(self.actions_panel_width)

        actions_layout = QVBoxLayout(self.actions_panel)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)

        self.actions_title = QLabel("ACTIONS")
        self.actions_title.setObjectName("title")
        actions_layout.addWidget(self.actions_title)

        self.player_scan_button = QPushButton("SAVE LOADOUT")
        self.player_scan_button.setObjectName("playerScan")
        self.player_scan_button.setEnabled(False)
        self.player_scan_button.setMinimumHeight(36)
        self.player_scan_button.setToolTip(
            "Scan your current inventory to create a loadout"
        )
        self.player_scan_button.clicked.connect(self.scan_player_inventory)
        actions_layout.addWidget(self.player_scan_button)

        self.clear_loadout_button = QPushButton("CLEAR INVENTORY")
        self.clear_loadout_button.setObjectName("clearLoadout")
        self.clear_loadout_button.setEnabled(False)
        self.clear_loadout_button.setMinimumHeight(36)
        self.clear_loadout_button.setToolTip(
            "Double-click recognized items in your player inventory"
        )
        self.clear_loadout_button.clicked.connect(self.clear_player_inventory)
        actions_layout.addWidget(self.clear_loadout_button)

        # Spinner, result message, and OK button are stacked vertically.

        self.loadout_result_widget = QWidget()
        self.loadout_result_widget.setObjectName("loadoutResultContainer")

        result_layout = QVBoxLayout(self.loadout_result_widget)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(8)

        self.spinner_label = QLabel("◐")
        self.spinner_label.setObjectName("spinner")
        self.spinner_label.setStyleSheet(
            "font-family: 'Segoe UI Symbol'; "
            "font-size: 16pt; "
            "font-weight: bold; "
            "color: #6df5c4; "
            "background: transparent;"
        )
        self.spinner_label.setFixedWidth(48)
        self.spinner_label.setMinimumHeight(55)
        self.spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spinner_label.hide()

        result_layout.addWidget(
            self.spinner_label,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )

        self.loadout_result_label = QLabel()
        self.loadout_result_label.setObjectName("loadoutResultText")
        self.loadout_result_label.setWordWrap(True)
        self.loadout_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loadout_result_label.setMinimumHeight(40)
        self.loadout_result_label.setContentsMargins(0, 0, 0, 0)
        self.loadout_result_label.hide()

        result_layout.addWidget(self.loadout_result_label)

        # OK appears underneath the missing-items message.
        self.loadout_result_ok_button = QPushButton("OK")
        self.loadout_result_ok_button.setObjectName("loadoutResultOkButton")
        self.loadout_result_ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loadout_result_ok_button.setFixedSize(55, 30)
        self.loadout_result_ok_button.clicked.connect(self.hide_loadout_result)
        self.loadout_result_ok_button.hide()

        result_layout.addWidget(
            self.loadout_result_ok_button,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self.loadout_result_widget.hide()
        actions_layout.addWidget(self.loadout_result_widget)

        actions_layout.setSpacing(8)

        # Completed-result countdown bar.

        self.loadout_result_progress = QProgressBar()
        self.loadout_result_progress.setObjectName("loadoutResultProgress")
        self.loadout_result_progress.setRange(0, 2500)
        self.loadout_result_progress.setValue(2500)
        self.loadout_result_progress.setTextVisible(False)
        self.loadout_result_progress.setFixedHeight(6)
        self.loadout_result_progress.hide()

        actions_layout.addWidget(self.loadout_result_progress)
        actions_layout.addStretch(1)

        self.hint = QLabel("F10  ·  Show / Hide")
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        actions_layout.addWidget(self.hint)

        # LOADOUTS PANEL

        self.loadouts_panel = QWidget()
        self.loadouts_panel.setObjectName("loadoutsPanel")
        self.loadouts_panel.setFixedWidth(self.loadouts_panel_width)

        loadouts_layout = QVBoxLayout(self.loadouts_panel)
        loadouts_layout.setContentsMargins(0, 0, 0, 0)
        loadouts_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.loadout_title = QLabel("LOADOUTS")
        self.loadout_title.setObjectName("title")
        header.addWidget(self.loadout_title)
        header.addStretch(1)

        loadouts_layout.addLayout(header)

        self.loadout_list = QVBoxLayout()
        self.loadout_list.setContentsMargins(0, 0, 0, 0)
        self.loadout_list.setSpacing(8)

        self.loadout_container = QWidget()
        self.loadout_container.setLayout(self.loadout_list)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("loadoutScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.loadout_container)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setMinimumWidth(0)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        loadouts_layout.addWidget(self.scroll_area, 1)

        # LOADOUT DETAILS PANEL

        self.details_panel = QWidget()
        self.details_panel.setObjectName("detailsPanel")
        self.details_panel.setMinimumWidth(0)
        self.details_panel.setMaximumWidth(0)

        details_layout = QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)

        details_header = QHBoxLayout()
        details_header.setContentsMargins(0, 0, 0, 0)
        details_header.setSpacing(6)

        self.details_title = QLabel("VIEWING")
        self.details_title.setObjectName("title")
        details_header.addWidget(self.details_title)

        self.details_loadout_name = QLabel("")
        self.details_loadout_name.setObjectName("loadoutName")
        self.details_loadout_name.setWordWrap(True)
        details_header.addWidget(self.details_loadout_name, 1)

        details_layout.addLayout(details_header)

        self.details_scroll_area = QScrollArea()
        self.details_scroll_area.setObjectName("detailsScrollArea")
        self.details_scroll_area.setWidgetResizable(True)
        self.details_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.details_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.details_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.details_scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.details_content_host = QWidget()
        self.details_content_layout = QVBoxLayout(self.details_content_host)
        self.details_content_layout.setContentsMargins(0, 0, 0, 0)
        self.details_content_layout.setSpacing(0)

        self.details_scroll_area.setWidget(self.details_content_host)
        details_layout.addWidget(self.details_scroll_area, 1)

        self.details_panel.hide()

        layout.addWidget(self.actions_panel, 0)
        layout.addWidget(self.loadouts_panel, 0)
        layout.addWidget(self.details_panel, 0)

        self.ui_stack = QStackedWidget()
        self.ui_stack.setContentsMargins(0, 0, 0, 0)
        self.ui_stack.addWidget(root)
        self.ui_stack.setCurrentWidget(root)

    def _build_title_bar(self):

        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(self.title_bar_height)

        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(6)

        self.header_title = QLabel("RaiderKit")
        self.header_title.setObjectName("windowTitle")
        layout.addWidget(self.header_title)

        layout.addStretch()

        for text, name, tip, callback in (
            ("Hide", "hideButton", "Hide overlay to tray", self.hide),
            ("Shut Down", "closeButton", "Quit RaiderKit", self.quit_app),
        ):

            button = QPushButton(text)
            button.setObjectName(name)
            button.setFixedSize(
                70 if name == "closeButton" else 50,
                28,
            )
            button.setToolTip(tip)
            button.clicked.connect(callback)
            layout.addWidget(button)

            if name == "hideButton":
                self.hide_button = button
            else:
                self.close_button = button

    def _build_central_frame(self):

        self.central_frame = QWidget()
        self.central_frame.setObjectName("centralFrame")

        layout = QVBoxLayout(self.central_frame)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        layout.addWidget(self.title_bar)
        layout.addWidget(self.ui_stack, 1)

        self.setCentralWidget(self.central_frame)

    def _setup_timers(self):

        self.scan_spinner_timer = QTimer(self)
        self.scan_spinner_timer.setInterval(100)
        self.scan_spinner_timer.timeout.connect(self._animate_scan_spinner)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.timeout.connect(self.update_player_inventory_results)
        self.status_timer.timeout.connect(self.update_loadout_results)
        self.status_timer.start(100)

        self.scan_restore_timer = QTimer(self)
        self.scan_restore_timer.setInterval(100)
        self.scan_restore_timer.timeout.connect(self.check_player_scan_finished)

        self.loadout_result_timer = QTimer(self)
        self.loadout_result_timer.setInterval(self.loadout_result_tick)
        self.loadout_result_timer.timeout.connect(self._advance_loadout_result)
