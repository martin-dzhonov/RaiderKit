import copy
import main as automation
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from common import (
    ACTIONS_PANEL_WIDTH,
    ITEM_NAMES,
    LOADOUTS_PANEL_WIDTH,
    NORMAL_HEIGHT,
    TITLE_BAR_HEIGHT,
    drain_queue,
    read_loadouts,
)
from overlay_ui import OverlayUIMixin
from overlay_loadouts import OverlayLoadoutsMixin


class InventoryOverlay(OverlayUIMixin, OverlayLoadoutsMixin, QMainWindow):

    def __init__(
        self,
        process_generated_loadout,
        delete_loadout,
        initialization_worker_class,
    ):
        super().__init__()

        self.process_generated_loadout = process_generated_loadout
        self.delete_loadout_operation = delete_loadout
        self.initialization_worker_class = initialization_worker_class

        self.setWindowTitle("RaiderKit")

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self.initialization_complete = False
        self.initialization_failed = False
        self.init_worker = None

        self.normal_height = NORMAL_HEIGHT
        self.title_bar_height = TITLE_BAR_HEIGHT
        self.actions_panel_width = ACTIONS_PANEL_WIDTH
        self.loadouts_panel_width = LOADOUTS_PANEL_WIDTH

        self.compact_mode = False

        self.loadouts = read_loadouts()

        # Successful loadout result countdown.
        self.loadout_result_duration = 650
        self.loadout_result_tick = 50
        self.loadout_result_remaining = 0
        self.loadout_result_visible = False

        # Scanning spinner.
        self.scan_progress_visible = False
        self.scan_status_message = ""
        self.scan_spinner_frames = ["◐", "◓", "◑", "◒"]
        self.scan_spinner_index = 0

        self.normal_width = self.calculate_window_width()

        self.resize(self.normal_width * 2 + 80, self.normal_height)
        self.center_at_top()

        self._build_main_panel()
        self._build_title_bar()
        self._build_central_frame()
        self._setup_timers()

        self.refresh_loadouts()

    def start_initialization(self):
        if self.init_worker is not None:
            return

        self.initialization_complete = False
        self.initialization_failed = False

        self.status.setText("●  Loading assets...")
        self.player_scan_button.setEnabled(False)
        self.clear_loadout_button.setEnabled(False)

        self.init_worker = self.initialization_worker_class(self)
        self.init_worker.initialized.connect(self.on_initialization_finished)
        self.init_worker.failed.connect(self.on_initialization_failed)
        self.init_worker.start()

    def on_initialization_finished(self):
        self.initialization_complete = True
        self.initialization_failed = False

        self.player_scan_button.setEnabled(True)
        self.clear_loadout_button.setEnabled(True)

        self.status.setText("●  Ready")
        self.refresh_loadouts()

    def on_initialization_failed(self, error):
        self.initialization_complete = False
        self.initialization_failed = True

        self.player_scan_button.setEnabled(False)
        self.clear_loadout_button.setEnabled(False)

        self.status.setText("●  Asset initialization failed")
        self.refresh_loadouts()

        QMessageBox.critical(
            self,
            "Initialization Error",
            f"Could not initialize RaiderKit:\n{error}",
        )

    def center_at_top(self):
        screen = QApplication.primaryScreen()

        if screen is None:
            return

        geometry = screen.availableGeometry()

        self.move(
            geometry.left() + 150,
            geometry.top(),
        )

    def show_scan_progress(self, message):
        """Show the large animated spinner without a progress bar."""

        self.loadout_result_timer.stop()
        self.loadout_result_progress.hide()
        self.loadout_result_ok_button.hide()

        self.loadout_result_visible = False
        self.scan_progress_visible = True
        self.scan_status_message = str(message)
        self.scan_spinner_index = 0

        self.player_scan_button.hide()
        self.clear_loadout_button.hide()

        self.spinner_label.setText(self.scan_spinner_frames[0])
        self.spinner_label.show()

        self.loadout_result_label.setProperty("resultType", "progress")
        self.loadout_result_label.setText(self.scan_status_message)
        self.loadout_result_label.show()
        self.loadout_result_widget.show()

        self.loadout_result_label.style().unpolish(self.loadout_result_label)
        self.loadout_result_label.style().polish(self.loadout_result_label)

        if not self.scan_spinner_timer.isActive():
            self.scan_spinner_timer.start()

    def _animate_scan_spinner(self):
        """Animate only the large spinner; keep status text unchanged."""

        if not self.scan_progress_visible:
            self.scan_spinner_timer.stop()
            return

        self.scan_spinner_index = (self.scan_spinner_index + 1) % len(
            self.scan_spinner_frames
        )

        self.spinner_label.setText(self.scan_spinner_frames[self.scan_spinner_index])

    def hide_scan_progress(self):
        """Stop the spinner and restore controls when appropriate."""

        self.scan_spinner_timer.stop()
        self.scan_progress_visible = False
        self.scan_status_message = ""

        if not self.loadout_result_visible:
            self.spinner_label.hide()
            self.loadout_result_widget.hide()
            self.loadout_result_progress.hide()
            self.loadout_result_ok_button.hide()

            if self.initialization_complete:
                self.player_scan_button.show()
                self.clear_loadout_button.show()

    def _start_scan(
        self,
        start,
        label,
        status,
        running_message="●  A scan is already running.",
        prepare=None,
    ):
        if not self.initialization_complete:
            self.status.setText("●  Assets are still loading.")
            return

        if automation.task_running:
            self.status.setText(running_message)
            return

        if prepare:
            prepare()

        self.hide_loadout_result()
        self.status.setText(status)
        self.show_scan_progress(label)

        try:
            start()

        except Exception as exc:
            self.scan_restore_timer.stop()
            self.hide_scan_progress()

            self.status.setText(f"●  Could not start task: {exc}")

            QMessageBox.critical(
                self,
                "Task Error",
                f"Could not start task:\n{exc}",
            )
            return

        if automation.task_running:
            self.scan_restore_timer.start()
        else:
            self.hide_scan_progress()

    def scan_player_inventory(self):
        self._start_scan(
            automation.scan_player_inventory,
            "Scanning player inventory...",
            "●  Scanning visible inventory grid...",
            running_message="●  Please wait for the current task to finish.",
            prepare=lambda: drain_queue(automation.player_inventory_results),
        )

    def clear_player_inventory(self):
        if not hasattr(automation, "clear_player_inventory"):
            QMessageBox.critical(
                self,
                "Clear Inventory Error",
                "main.py does not define clear_player_inventory().",
            )
            return

        self._start_scan(
            automation.clear_player_inventory,
            "Unloading Inventory",
            "●  Clearing recognized inventory items...",
            running_message="●  Please wait for the current task to finish.",
        )

    def start_loadout_scan(self, name):
        loadout = self.loadouts.get(name)

        if loadout is None:
            return

        drain_queue(automation.loadout_results)

        self._start_scan(
            lambda: automation.start_scan(copy.deepcopy(loadout)),
            "Scanning stash",
            f"●  Starting loadout: {name}",
            running_message="●  Please wait for the current task to finish.",
        )

    def check_player_scan_finished(self):
        """Clean up scanning UI when the automation task finishes."""

        if automation.task_running:
            return

        self.scan_restore_timer.stop()

        self.update_status()
        self.update_player_inventory_results()
        self.update_loadout_results()

        if self.scan_progress_visible and not self.loadout_result_visible:
            self.hide_scan_progress()

    def update_player_inventory_results(self):
        if not self.initialization_complete:
            return

        for loadout in drain_queue(automation.player_inventory_results):
            self.process_generated_loadout(self, loadout)

    def update_loadout_results(self):
        """Display the newest completed stash loadout result."""

        if not self.initialization_complete:
            return

        results = drain_queue(automation.loadout_results)

        if not results:
            return

        result = results[-1]

        if result.get("success"):
            message = "LOADOUT EQUIPPED"
            result_type = "success"

        else:
            missing = result.get("missing", {})

            if missing:
                missing_lines = "\n".join(
                    f"• {ITEM_NAMES.get(name, name)} x{quantity}"
                    for name, quantity in missing.items()
                    if quantity > 0
                )

                message = (
                    f"Couldn't find items:\n{missing_lines}"
                    if missing_lines
                    else "Loadout could not be verified."
                )
            else:
                message = "Loadout could not be verified."

            result_type = "missing"

        self.show_loadout_result(message, result_type)

    def show_loadout_result(self, message, result_type=None):
        """Show success briefly, or missing items until OK is clicked."""

        self.scan_spinner_timer.stop()
        self.scan_progress_visible = False
        self.scan_status_message = ""

        self.loadout_result_timer.stop()
        self.loadout_result_visible = True

        self.player_scan_button.hide()
        self.clear_loadout_button.hide()
        self.spinner_label.hide()

        if result_type is not None:
            self.loadout_result_label.setProperty("resultType", result_type)

        self.loadout_result_label.setText(message)
        self.loadout_result_label.show()
        self.loadout_result_widget.show()

        self.loadout_result_label.style().unpolish(self.loadout_result_label)
        self.loadout_result_label.style().polish(self.loadout_result_label)

        if result_type == "success":
            # Success: show the progress bar and start the countdown.
            self.loadout_result_ok_button.hide()

            self.loadout_result_remaining = self.loadout_result_duration

            self.loadout_result_progress.setRange(0, self.loadout_result_duration)
            self.loadout_result_progress.setValue(self.loadout_result_duration)
            self.loadout_result_progress.show()

            self.loadout_result_timer.start()

        else:
            # Missing items: remain visible until OK is clicked.
            self.loadout_result_remaining = 0
            self.loadout_result_progress.hide()
            self.loadout_result_ok_button.show()

    def _advance_loadout_result(self):
        """Decrease the success countdown bar until the result expires."""

        if not self.loadout_result_visible:
            self.loadout_result_timer.stop()
            return

        self.loadout_result_remaining = max(
            0,
            self.loadout_result_remaining - self.loadout_result_tick,
        )

        self.loadout_result_progress.setValue(self.loadout_result_remaining)

        if self.loadout_result_remaining <= 0:
            self.hide_loadout_result()

    def hide_loadout_result(self):
        """Hide the result message and restore the main overlay controls."""

        self.loadout_result_timer.stop()
        self.loadout_result_visible = False
        self.loadout_result_remaining = 0

        if not hasattr(self, "loadout_result_label"):
            return

        self.loadout_result_progress.hide()
        self.loadout_result_ok_button.hide()

        if self.scan_progress_visible:
            return

        self.spinner_label.hide()
        self.loadout_result_widget.hide()

        if self.initialization_complete:
            self.player_scan_button.show()
            self.clear_loadout_button.show()

    def load_loadout(self, name):
        self.start_loadout_scan(name)

    def update_status(self):
        """Update status text and the Actions-panel scanning message."""

        messages = drain_queue(automation.status_queue)

        if not messages:
            return

        message = str(messages[-1])

        if not self.initialization_complete:
            return

        self.status.setText(message)

        if self.scan_progress_visible and automation.task_running:
            self.scan_status_message = message
            self.loadout_result_label.setText(message)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def quit_app(self):
        QApplication.quit()

    def stop_initialization(self):
        if self.init_worker is not None and self.init_worker.isRunning():
            self.init_worker.wait()
