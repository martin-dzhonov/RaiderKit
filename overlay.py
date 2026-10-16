import copy
import logging
import re
import main as automation
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from common import (
    ITEM_NAMES,
    WINDOW_HEIGHT,
    WINDOW_FIXED_WIDTH,
    drain_queue,
    get_item_categories,
    read_loadouts,
    read_loadout_tab_options,
    save_loadout_tab_options,
)
from overlay_ui import OverlayUIMixin
from overlay_loadouts import OverlayLoadoutsMixin

logger = logging.getLogger(__name__)


def enabled_stash_tabs(options):
    return {
        category
        for category in get_item_categories()
        if options.get(category, True)
    }


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.initialization_complete = False
        self.initialization_failed = False
        self.init_worker = None

        self.compact_mode = False
        self.inventory_save_layout = None
        self.inventory_save_worker = None
        self.loadout_equip_progress_bars = {}
        self.loadout_equip_animations = {}

        self.loadouts = read_loadouts()
        self.loadout_tab_options = read_loadout_tab_options(self.loadouts)

        # Successful loadout result countdown.
        self.loadout_result_duration = 650
        self.loadout_result_tick = 50
        self.loadout_result_remaining = 0
        self.loadout_result_visible = False

        # Scanning spinner.
        self.scan_progress_visible = False
        self.scan_status_message = ""
        self.scan_progress_updates_from_status = True

        self.setFixedHeight(WINDOW_HEIGHT)

        self._build_main_panel()
        self._build_title_bar()
        self._build_central_frame()
        self._setup_timers()

        self.refresh_loadouts()
        self.center_at_top()

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
            geometry.left() + 157,
            geometry.top(),
        )

    def collapse_for_inventory_save(self):
        if self.inventory_save_layout is not None:
            return

        self.inventory_save_layout = (
            self.width(),
            self.loadouts_panel.isVisible(),
            self.panel_divider.isVisible(),
        )
        self.loadouts_panel.hide()
        self.panel_divider.hide()
        self.setFixedWidth(WINDOW_FIXED_WIDTH)
        QApplication.processEvents()
        logger.info(
            "Inventory save: collapsed overlay to %d px before inventory scans",
            self.width(),
        )

    def restore_after_inventory_save(self):
        if self.inventory_save_layout is None:
            return

        previous_width, loadouts_were_visible, divider_was_visible = (
            self.inventory_save_layout
        )
        self.setFixedWidth(previous_width)
        if loadouts_were_visible:
            self.loadouts_panel.show()
        if divider_was_visible:
            self.panel_divider.show()
        self.inventory_save_layout = None
        QApplication.processEvents()
        logger.info(
            "Inventory save: restored overlay to %d px",
            self.width(),
        )

    def show_scan_progress(
        self,
        message,
        update_from_status=True,
        show_cancel_hint=False,
    ):
        """Show the repeating progress bar while a scan is running."""

        self.loadout_result_timer.stop()
        self.loadout_result_ok_button.hide()

        self.loadout_result_visible = False
        self.scan_progress_visible = True
        self.scan_status_message = str(message)
        self.scan_progress_updates_from_status = update_from_status

        self.player_scan_button.hide()
        self.clear_loadout_button.hide()

        self.scan_progress_bar.setValue(0)
        self.scan_progress_bar.setRange(0, 1000)
        self.scan_progress_bar.show()
        self.scan_cancel_hint.show()

        self.loadout_result_label.setProperty("resultType", "progress")
        self.loadout_result_label.setText(self.scan_status_message)
        self.loadout_result_label.show()
        self.loadout_result_widget.show()

        self.loadout_result_label.style().unpolish(self.loadout_result_label)
        self.loadout_result_label.style().polish(self.loadout_result_label)

        self.scan_progress_animation.stop()
        self.scan_progress_animation.setCurrentTime(0)
        self.scan_progress_animation.start()

    def hide_scan_progress(self):
        """Stop the progress animation and restore controls when appropriate."""

        self.scan_progress_animation.stop()
        self.scan_progress_visible = False
        self.scan_status_message = ""
        self.scan_progress_updates_from_status = True

        if not self.loadout_result_visible:
            self.scan_progress_bar.hide()
            self.scan_cancel_hint.hide()
            self.loadout_result_widget.hide()
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
        update_progress_message=True,
        show_cancel_hint=False,
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
        self.show_scan_progress(
            label,
            update_progress_message,
            show_cancel_hint=show_cancel_hint,
        )

        try:
            start()

        except Exception as exc:
            self.scan_restore_timer.stop()
            self.set_loadout_equip_progress(None)
            self.restore_after_inventory_save()
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
            self.set_loadout_equip_progress(None)
            self.restore_after_inventory_save()
            self.hide_scan_progress()

    def scan_player_inventory(self):
        self._start_scan(
            automation.scan_player_inventory,
            "Scanning player inventory...",
            "●  Scanning visible inventory grid...",
            running_message="●  Please wait for the current task to finish.",
            prepare=self._prepare_player_inventory_scan,
            show_cancel_hint=True,
        )

    def _prepare_player_inventory_scan(self):
        drain_queue(automation.player_inventory_results)
        self.collapse_for_inventory_save()

    def cancel_current_task(self):
        if not (
            automation.task_running
            or self.inventory_save_worker is not None
            or self.scan_progress_visible
        ):
            return

        logger.info("Space pressed: cancelling the current save/load operation")
        automation.scan_cancel_event.set()

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
            lambda: automation.start_scan(
                copy.deepcopy(loadout),
                enabled_tabs=enabled_stash_tabs(
                    self.loadout_tab_options.get(name, {})
                ),
            ),
            f"Equipping\n{name}",
            f"●  Starting loadout: {name}",
            running_message="●  Please wait for the current task to finish.",
            prepare=lambda: self.set_loadout_equip_progress(name),
            update_progress_message=False,
        )

    def update_loadout_tab_option(self, name, category, enabled):
        previous_options = self.loadout_tab_options.get(
            name,
            {category: True for category in get_item_categories()},
        )
        updated_options = {**previous_options, category: enabled}
        self.loadout_tab_options[name] = updated_options
        try:
            save_loadout_tab_options(self.loadout_tab_options)
        except OSError as exc:
            self.loadout_tab_options[name] = previous_options
            QMessageBox.critical(
                self,
                "Loadout Options Save Failed",
                f"Could not save equip options for '{name}':\n\n{exc}",
            )
            self.refresh_loadouts()

    def check_player_scan_finished(self):
        """Clean up scanning UI when the automation task finishes."""

        if automation.task_running:
            return

        self.scan_restore_timer.stop()
        self.set_loadout_equip_progress(None)

        self.update_status()
        self.update_player_inventory_results()
        self.update_loadout_results()

        if self.inventory_save_worker is None:
            self.restore_after_inventory_save()

        if (
            self.inventory_save_worker is None
            and self.scan_progress_visible
            and not self.loadout_result_visible
        ):
            self.hide_scan_progress()

    def update_player_inventory_results(self):
        if not self.initialization_complete or automation.task_running:
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

        self.set_loadout_equip_progress(None)
        result = results[-1]

        if result.get("error"):
            message = f"Equip failed:\n{result['error']}"
            result_type = "missing"

        elif result.get("success"):
            message = "LOADOUT EQUIPPED"
            result_type = "success"

        else:
            missing = result.get("missing", {})

            if missing:
                missing_lines = "\n".join(
                    self._format_missing_item(name, quantity)
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

    @staticmethod
    def _format_missing_item(name, quantity):
        display_name = ITEM_NAMES.get(name, name)

        if name in get_item_categories().get("weapons", set()):
            # Weapon keys look like "STITCHER IV_02"; drop the "_02" suffix.
            display_name = re.sub(r"_\d+$", "", display_name)

        return f"• {display_name}" + (f" x{quantity}" if quantity != 1 else "")

    def show_loadout_result(self, message, result_type=None):
        """Show success briefly, or missing items until OK is clicked."""

        self.scan_progress_visible = False
        self.scan_status_message = ""

        self.loadout_result_timer.stop()
        self.loadout_result_visible = True

        self.player_scan_button.hide()
        self.clear_loadout_button.hide()
        self.scan_cancel_hint.hide()

        if result_type is not None:
            self.loadout_result_label.setProperty("resultType", result_type)

        self.loadout_result_label.setText(message)
        self.loadout_result_label.show()
        self.loadout_result_widget.show()

        self.loadout_result_label.style().unpolish(self.loadout_result_label)
        self.loadout_result_label.style().polish(self.loadout_result_label)

        if result_type == "success":
            # Keep the active scan animation visible while showing success.
            self.loadout_result_ok_button.hide()

            self.loadout_result_remaining = self.loadout_result_duration

            self.scan_progress_bar.setRange(0, 1000)
            self.scan_progress_bar.show()

            self.loadout_result_timer.start()

        else:
            # Missing items: remain visible until OK is clicked.
            self.scan_progress_animation.stop()
            self.loadout_result_remaining = 0
            self.scan_progress_bar.hide()
            self.scan_cancel_hint.hide()
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

        if self.loadout_result_remaining <= 0:
            self.hide_loadout_result()

    def hide_loadout_result(self):
        """Hide the result message and restore the main overlay controls."""

        self.loadout_result_timer.stop()
        self.scan_progress_animation.stop()
        self.loadout_result_visible = False
        self.loadout_result_remaining = 0

        if not hasattr(self, "loadout_result_label"):
            return

        self.loadout_result_ok_button.hide()

        if self.scan_progress_visible:
            return

        self.scan_progress_bar.hide()
        self.scan_cancel_hint.hide()
        self.loadout_result_widget.hide()

        if self.initialization_complete:
            self.player_scan_button.show()
            self.clear_loadout_button.show()

    def load_loadout(self, name):
        self.start_loadout_scan(name)

    def update_status(self):
        """Update status text and the loadouts-panel scanning message."""

        messages = drain_queue(automation.status_queue)

        if not messages:
            return

        message = str(messages[-1])

        if not self.initialization_complete:
            return

        self.status.setText(message)

        if (
            self.scan_progress_visible
            and self.scan_progress_updates_from_status
            and automation.task_running
        ):
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
