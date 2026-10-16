import copy
import logging
import sys
import threading

from pynput import keyboard
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

import main as automation
from common import (
    TEMPLATE_DIR,
    flatten_loadout,
    get_item_categories,
    refresh_item_categories,
    save_loadouts,
    save_loadout_tab_options,
    validate_loadout,
)
from dialogs import GeneratedLoadoutDialog
from overlay import InventoryOverlay
from common import load_stylesheet

logger = logging.getLogger(__name__)


class InitializationWorker(QThread):
    """Run automation initialization without blocking the UI."""

    initialized = Signal()
    failed = Signal(str)

    def run(self):
        try:
            automation.initialize()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.initialized.emit()


class FinalInventoryActionsWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, initial_image, parent=None):
        super().__init__(parent)
        self.initial_image = initial_image

    def run(self):
        try:
            weapon_item_ids = automation.perform_player_inventory_save_actions(
                initial_image=self.initial_image,
            )
        except automation.ScanCancelled:
            logger.info("Final inventory actions cancelled")
            self.cancelled.emit()
        except Exception as exc:
            logger.exception("Final inventory actions failed")
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(weapon_item_ids)


class HotkeyListener:
    """Listen for F5 visibility toggles and Space cancellation globally."""

    def __init__(self, callback, cancel_callback):
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.listener = keyboard.GlobalHotKeys(
            {
                "<f5>": self._on_f5,
                "<space>": self._on_cancel,
            }
        )
        self.listener.start()

    def _on_f5(self):
        # pynput invokes this from its listener thread.
        self.callback()

    def _on_cancel(self):
        self.cancel_callback()

    def stop(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None


def process_generated_loadout(overlay, inventory_scan):
    """Run final inventory actions asynchronously before building the loadout."""
    if overlay.inventory_save_worker is not None:
        return

    try:
        logger.info("Starting final inventory actions for generated loadout")
        worker = FinalInventoryActionsWorker(inventory_scan["image"], overlay)
        overlay.inventory_save_worker = worker
        worker.succeeded.connect(
            lambda weapon_item_ids: finish_generated_loadout(
                overlay,
                inventory_scan,
                weapon_item_ids,
            )
        )
        worker.failed.connect(
            lambda error: handle_inventory_actions_failure(overlay, error)
        )
        worker.cancelled.connect(lambda: handle_inventory_actions_cancelled(overlay))
        worker.finished.connect(lambda: setattr(overlay, "inventory_save_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()
    except Exception:
        overlay.inventory_save_worker = None
        logger.exception("Could not start final inventory actions")
        handle_inventory_actions_failure(
            overlay,
            "The background task could not be started. See the application log.",
        )


def handle_inventory_actions_failure(overlay, error):
    overlay.restore_after_inventory_save()
    overlay.hide_scan_progress()
    overlay.status.setText("Final inventory actions failed; loadout was not saved.")
    QMessageBox.critical(
        overlay,
        "Inventory Save Failed",
        f"The final inventory actions or screenshot failed:\n\n{error}\n\n"
        "The generated loadout was not saved.",
    )


def handle_inventory_actions_cancelled(overlay):
    overlay.restore_after_inventory_save()
    overlay.hide_scan_progress()
    overlay.status.setText("Inventory save cancelled.")


def finish_generated_loadout(overlay, inventory_scan, weapon_item_ids):
    """Restore the overlay, then validate and prompt to save the generated loadout."""
    overlay.restore_after_inventory_save()
    overlay.hide_scan_progress()

    try:
        weapon_items = [
            {"name": item_id, "banner_text": "1"} for item_id in weapon_item_ids
        ]
        loadout = automation.utils.build_player_loadout(
            inventory_scan["main_items"] + weapon_items,
            inventory_scan["quickuse_items"],
        )

        # Flattening checks that the generated structure can be processed.
        flatten_loadout(loadout)
        validate_loadout("Generated Loadout", loadout)
    except ValueError as exc:
        overlay.status.setText(f"Generated loadout is invalid: {exc}")
        QMessageBox.warning(
            overlay,
            "Invalid Loadout",
            f"The generated loadout could not be saved:\n\n{exc}",
        )
        return
    except Exception:
        logger.exception("Could not build generated loadout")
        overlay.status.setText("Could not build generated loadout.")
        QMessageBox.critical(
            overlay,
            "Loadout Generation Failed",
            "The generated loadout could not be prepared. "
            "See the application log for details.",
        )
        return

    try:
        dialog = GeneratedLoadoutDialog(
            loadout,
            overlay.loadouts.keys(),
            overlay,
        )

        if dialog.exec() != GeneratedLoadoutDialog.DialogCode.Accepted:
            overlay.status.setText("Generated loadout discarded.")
            return

        name = dialog.loadout_name
        updated_loadouts = {
            **overlay.loadouts,
            name: copy.deepcopy(dialog.loadout_data),
        }
        save_loadouts(updated_loadouts)
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("Could not save generated loadout")
        overlay.status.setText("Failed to save generated loadout.")
        QMessageBox.critical(
            overlay,
            "Save Failed",
            f"Could not save the generated loadout:\n\n{exc}",
        )
        return
    except Exception:
        logger.exception("Unexpected failure while saving generated loadout")
        overlay.status.setText("Failed to save generated loadout.")
        QMessageBox.critical(
            overlay,
            "Save Failed",
            "An unexpected error occurred while saving the generated loadout. "
            "See the application log for details.",
        )
        return

    overlay.loadouts = updated_loadouts
    overlay.refresh_loadouts()
    overlay.status.setText(f"Saved generated loadout: {name}")


def delete_weapon_assets(deleted_loadout):
    """Remove the weapon template images used by the deleted loadout."""
    try:
        weapon_names = get_item_categories().get("weapons", set())
        deleted_weapons = {
            item
            for item in flatten_loadout(deleted_loadout)
            if item in weapon_names
        }

        if not deleted_weapons:
            return

        weapons_dir = TEMPLATE_DIR / "weapons"
        for path in weapons_dir.iterdir():
            if path.is_file() and path.stem in deleted_weapons:
                path.unlink()
                logger.info("Deleted weapon asset: %s", path)

        refresh_item_categories()
    except Exception:
        logger.exception("Could not delete weapon assets for deleted loadout")


def delete_loadout(overlay, name):
    """Ask for confirmation and delete a saved loadout."""
    answer = QMessageBox.question(
        overlay,
        "Delete Loadout",
        f"Are you sure you want to delete '{name}'?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )

    if answer != QMessageBox.StandardButton.Yes:
        return

    if name not in overlay.loadouts:
        return

    deleted_loadout = overlay.loadouts[name]

    updated_loadouts = {
        loadout_name: loadout
        for loadout_name, loadout in overlay.loadouts.items()
        if loadout_name != name
    }

    try:
        save_loadouts(updated_loadouts)
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("Could not delete loadout '%s'", name)
        overlay.status.setText("Failed to delete loadout.")
        QMessageBox.critical(
            overlay,
            "Delete Failed",
            f"Could not delete '{name}':\n\n{exc}",
        )
        return
    except Exception:
        logger.exception("Unexpected failure deleting loadout '%s'", name)
        overlay.status.setText("Failed to delete loadout.")
        QMessageBox.critical(
            overlay,
            "Delete Failed",
            "An unexpected error occurred while deleting this loadout. "
            "See the application log for details.",
        )
        return

    overlay.loadouts = updated_loadouts
    updated_options = dict(overlay.loadout_tab_options)
    updated_options.pop(name, None)
    overlay.loadout_tab_options = updated_options
    try:
        save_loadout_tab_options(updated_options)
    except (OSError, TypeError, ValueError) as exc:
        logger.exception(
            "Could not remove equip options for deleted loadout '%s'", name
        )
        QMessageBox.warning(
            overlay,
            "Equip Options Cleanup Failed",
            f"Deleted '{name}', but its saved equip options could not be removed:\n\n{exc}",
        )

    delete_weapon_assets(deleted_loadout)

    overlay.refresh_loadouts()
    overlay.status.setText(f"Deleted loadout: {name}")


def create_tray_icon(app, overlay):
    """Create the system-tray icon and its context menu."""
    tray = QSystemTrayIcon(
        app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
        app,
    )
    tray.setToolTip("RaiderKit")

    menu = QMenu()

    toggle_action = QAction("Show / Hide Overlay", menu)
    toggle_action.triggered.connect(overlay.toggle_visibility)
    menu.addAction(toggle_action)

    menu.addSeparator()

    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            overlay.toggle_visibility()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
    )

    return tray


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RaiderKit")
    app.setQuitOnLastWindowClosed(False)

    app.setStyleSheet(load_stylesheet())

    try:
        refresh_item_categories()
    except Exception as exc:
        logger.exception("Could not initialize item category index")
        QMessageBox.critical(
            None,
            "Item Categories",
            f"Could not build the item category index:\n\n{exc}",
        )
        return 1

    overlay = InventoryOverlay(
        process_generated_loadout=process_generated_loadout,
        delete_loadout=delete_loadout,
        initialization_worker_class=InitializationWorker,
    )

    tray = create_tray_icon(app, overlay)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()

    # Bridge the background hotkey thread to Qt's main thread.
    class HotkeyBridge(QThread):
        toggle_requested = Signal()
        cancel_requested = Signal()

    hotkey_bridge = HotkeyBridge()
    hotkey_bridge.toggle_requested.connect(overlay.toggle_visibility)
    hotkey_bridge.cancel_requested.connect(overlay.cancel_current_task)

    hotkey = HotkeyListener(
        hotkey_bridge.toggle_requested.emit,
        hotkey_bridge.cancel_requested.emit,
    )

    app.aboutToQuit.connect(hotkey.stop)
    app.aboutToQuit.connect(tray.hide)

    # Stop any overlay-owned timers or initialization work during shutdown.
    if hasattr(overlay, "stop_initialization"):
        app.aboutToQuit.connect(overlay.stop_initialization)

    overlay.show()
    overlay.raise_()

    QTimer.singleShot(0, overlay.start_initialization)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
