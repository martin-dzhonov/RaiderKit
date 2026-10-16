from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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
    ACTION_PANEL_BUTTON_WIDTH,
    ACTION_PANEL_PROGRESS_WIDTH,
    ACTIONS_PANEL_WIDTH,
    LOADOUT_CARD_GAP,
    LOADOUTS_EMPTY_PANEL_WIDTH,
    TITLE_BAR_HEIGHT,
)


class HorizontalWheelScrollArea(QScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scroll_target = None
        self._scroll_animation = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(400)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self._scroll_animation.finished.connect(self._on_scroll_animation_finished)

    def wheelEvent(self, event: QWheelEvent) -> None:
        angle_delta = event.angleDelta().x() or event.angleDelta().y()

        if angle_delta:
            scroll_amount = (
                angle_delta * self.horizontalScrollBar().singleStep() * 9 // 240
            )
        else:
            pixel_delta = event.pixelDelta()
            pixel_scroll = pixel_delta.x() or pixel_delta.y()
            scroll_amount = pixel_scroll * 3

        if scroll_amount:
            scroll_bar = self.horizontalScrollBar()
            current_value = scroll_bar.value()
            target_base = (
                self._scroll_target
                if self._scroll_target is not None
                else current_value
            )
            self._scroll_target = max(
                scroll_bar.minimum(),
                min(scroll_bar.maximum(), target_base - scroll_amount),
            )

            self._scroll_animation.stop()
            self._scroll_animation.setStartValue(current_value)
            self._scroll_animation.setEndValue(self._scroll_target)
            self._scroll_animation.start()

            event.accept()
            return

        super().wheelEvent(event)

    def _on_scroll_animation_finished(self):
        self._scroll_target = None


class OverlayUIMixin:

    def _build_main_panel(self):

        root = QWidget()
        root.setObjectName("mainPanel")

        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        self.status = QLabel("Loading assets...")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.status.hide()

        # ACTIONS PANEL

        self.actions_panel = QWidget()
        self.actions_panel.setObjectName("actionsPanel")
        self.actions_panel.setFixedWidth(ACTIONS_PANEL_WIDTH)

        actions_panel_layout = QGridLayout(self.actions_panel)
        actions_panel_layout.setContentsMargins(0, 0, 0, 0)
        actions_panel_layout.setSpacing(0)

        actions_content = QWidget()
        actions_content.setObjectName("actionsContent")
        actions_panel_layout.addWidget(actions_content, 0, 0)

        actions_layout = QVBoxLayout(actions_content)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addSpacing(35)

        self.player_scan_button = QPushButton("SAVE LOADOUT")
        self.player_scan_button.setObjectName("playerScan")
        self.player_scan_button.setEnabled(False)
        self.player_scan_button.setMinimumHeight(36)
        self.player_scan_button.setFixedWidth(ACTION_PANEL_BUTTON_WIDTH)
        self.player_scan_button.setToolTip(
            "Scan your current inventory to create a loadout"
        )
        self.player_scan_button.clicked.connect(self.scan_player_inventory)
        actions_layout.addWidget(
            self.player_scan_button,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        actions_layout.addSpacing(15)

        self.clear_loadout_button = QPushButton("CLEAR INVENTORY")
        self.clear_loadout_button.setObjectName("clearLoadout")
        self.clear_loadout_button.setEnabled(False)
        self.clear_loadout_button.setMinimumHeight(36)
        self.clear_loadout_button.setFixedWidth(ACTION_PANEL_BUTTON_WIDTH)
        self.clear_loadout_button.setToolTip(
            "Double-click recognized items in your player inventory"
        )
        self.clear_loadout_button.clicked.connect(self.clear_player_inventory)
        actions_layout.addWidget(
            self.clear_loadout_button,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        # Spinner, result message, and OK button are stacked vertically.

        self.loadout_result_widget = QWidget()
        self.loadout_result_widget.setObjectName("loadoutResultContainer")
        self.loadout_result_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        result_layout = QVBoxLayout(self.loadout_result_widget)
        result_layout.setContentsMargins(0, 0, 0, 60)
        result_layout.setSpacing(13)
        result_layout.addStretch(1)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setObjectName("scanProgressIndicator")
        self.scan_progress_bar.setRange(0, 1000)
        self.scan_progress_bar.setValue(0)
        self.scan_progress_bar.setTextVisible(False)
        self.scan_progress_bar.setFixedSize(ACTION_PANEL_PROGRESS_WIDTH, 6)
        self.scan_progress_bar.hide()

        self.loadout_result_label = QLabel()
        self.loadout_result_label.setObjectName("loadoutResultText")
        self.loadout_result_label.setWordWrap(True)
        self.loadout_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loadout_result_label.setMinimumHeight(40)
        self.loadout_result_label.setContentsMargins(0, 0, 0, 0)
        self.loadout_result_label.hide()

        result_layout.addWidget(self.loadout_result_label)
        result_layout.addWidget(
            self.scan_progress_bar,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        self.scan_cancel_hint = QLabel("[ESC] to cancel")
        self.scan_cancel_hint.setObjectName("scanCancelHint")
        self.scan_cancel_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_cancel_hint.hide()
        result_layout.addWidget(self.scan_cancel_hint)

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

        result_layout.addStretch(1)
        self.loadout_result_widget.hide()

        actions_layout.setSpacing(8)
        actions_layout.addStretch(1)

        # LOADOUTS PANEL

        self.loadouts_panel = QWidget()
        self.loadouts_panel.setObjectName("loadoutsPanel")
        self.loadouts_panel.setFixedWidth(LOADOUTS_EMPTY_PANEL_WIDTH)
        self.loadouts_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        loadouts_layout = QVBoxLayout(self.loadouts_panel)
        loadouts_layout.setContentsMargins(0, 0, 0, 0)
        loadouts_layout.setSpacing(8)

        self.loadout_list = QHBoxLayout()
        self.loadout_list.setContentsMargins(0, 0, 0, 0)
        self.loadout_list.setSpacing(LOADOUT_CARD_GAP)
        self.loadout_list.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        self.loadout_container = QWidget()
        self.loadout_container.setObjectName("loadoutContainer")
        self.loadout_container.setLayout(self.loadout_list)
        self.loadout_container.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )

        self.scroll_area = HorizontalWheelScrollArea()
        self.scroll_area.setObjectName("loadoutScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.loadout_container)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setMinimumWidth(0)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        loadouts_layout.addWidget(self.scroll_area, 1)

        self.panel_divider = QWidget()
        self.panel_divider.setObjectName("panelDivider")
        self.panel_divider.setFixedWidth(2)
        self.panel_divider.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )

        layout.addWidget(self.actions_panel, 0)
        layout.addWidget(self.panel_divider, 0)
        layout.addWidget(self.loadouts_panel, 1)
        actions_panel_layout.addWidget(self.loadout_result_widget, 0, 0)

        self.ui_stack = QStackedWidget()
        self.ui_stack.setContentsMargins(0, 0, 0, 0)
        self.ui_stack.addWidget(root)
        self.ui_stack.setCurrentWidget(root)

    def _build_title_bar(self):

        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(TITLE_BAR_HEIGHT)

        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(6)

        self.header_title = QLabel("RaiderKit")
        self.header_title.setObjectName("windowTitle")
        layout.addWidget(self.header_title)

        layout.addStretch()

        for text, name, tip, callback in (
            (
                "Hide · F5",
                "hideButton",
                "Hide overlay; press F5 to show or hide it",
                self.hide,
            ),
            ("Shut Down", "closeButton", "Quit RaiderKit", self.quit_app),
        ):

            button = QPushButton(text)
            button.setObjectName(name)
            button.setFixedSize(
                70 if name == "closeButton" else 82,
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.title_bar)
        layout.addWidget(self.ui_stack, 1)

        self.setCentralWidget(self.central_frame)

    def _setup_timers(self):

        self.scan_progress_animation = QPropertyAnimation(
            self.scan_progress_bar,
            b"value",
            self,
        )
        self.scan_progress_animation.setStartValue(0)
        self.scan_progress_animation.setEndValue(1000)
        self.scan_progress_animation.setDuration(1000)
        self.scan_progress_animation.setLoopCount(-1)
        self.scan_progress_animation.setEasingCurve(QEasingCurve.Type.Linear)

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
