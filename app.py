import copy
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
    flatten_loadout,
    save_loadouts,
    validate_loadout,
)
from dialogs import GeneratedLoadoutDialog
from overlay import InventoryOverlay
from common import load_stylesheet


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


class HotkeyListener:
    """Listen for F10 globally and request an overlay visibility toggle."""

    def __init__(self, callback):
        self.callback = callback
        self.listener = keyboard.GlobalHotKeys(
            {
                "<f10>": self._on_f10,
            }
        )
        self.listener.start()

    def _on_f10(self):
        # pynput invokes this from its listener thread.
        self.callback()

    def stop(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None


def process_generated_loadout(overlay, loadout):
    """Validate, prompt for a name, and save an automatically generated loadout."""
    try:
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

    try:
        screenshot_path, _ = automation.perform_player_inventory_save_actions(loadout)
    except Exception as exc:
        overlay.status.setText("Final inventory actions failed; loadout was not saved.")
        QMessageBox.critical(
            overlay,
            "Inventory Save Failed",
            f"The final inventory actions or screenshot failed:\n\n{exc}\n\n"
            "The generated loadout was not saved.",
        )
        return

    dialog = GeneratedLoadoutDialog(
        loadout,
        overlay.loadouts.keys(),
        overlay,
    )

    if dialog.exec() != GeneratedLoadoutDialog.DialogCode.Accepted:
        overlay.status.setText("Generated loadout discarded.")
        return

    name = dialog.loadout_name
    overlay.loadouts[name] = copy.deepcopy(dialog.loadout_data)

    try:
        save_loadouts(overlay.loadouts)
    except OSError as exc:
        overlay.loadouts.pop(name, None)
        overlay.status.setText("Failed to save generated loadout.")
        QMessageBox.critical(
            overlay,
            "Save Failed",
            f"Could not save the generated loadout:\n\n{exc}",
        )
        return

    overlay.refresh_loadouts()
    overlay.status.setText(
        f"Saved generated loadout: {name}; screenshot: {screenshot_path}"
    )


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

    removed_loadout = overlay.loadouts.pop(name, None)
    if removed_loadout is None:
        return

    try:
        save_loadouts(overlay.loadouts)
    except OSError as exc:
        # Restore the in-memory entry if the file could not be updated.
        overlay.loadouts[name] = removed_loadout
        overlay.refresh_loadouts()
        overlay.status.setText("Failed to delete loadout.")
        QMessageBox.critical(
            overlay,
            "Delete Failed",
            f"Could not delete '{name}':\n\n{exc}",
        )
        return

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

    hotkey_bridge = HotkeyBridge()
    hotkey_bridge.toggle_requested.connect(overlay.toggle_visibility)

    hotkey = HotkeyListener(hotkey_bridge.toggle_requested.emit)

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
