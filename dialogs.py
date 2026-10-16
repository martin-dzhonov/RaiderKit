import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common import flatten_loadout, validate_loadout
from overlay_loadouts import OverlayLoadoutsMixin


class CustomDialogHeader(QFrame):
    def __init__(self, title, dialog):
        super().__init__(dialog)

        self.dialog = dialog
        self.drag_position = None

        self.setObjectName("customDialogHeader")
        self.setFixedHeight(32)

        header_layout = QHBoxLayout(self)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("customDialogTitle")

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.dialog.frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            self.drag_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.dialog.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_position = None
        super().mouseReleaseEvent(event)


class GeneratedLoadoutDialog(OverlayLoadoutsMixin, QDialog):
    def __init__(self, loadout_data, existing_names, parent=None):
        super().__init__(parent)

        # Remove the native Windows title bar.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        self.setObjectName("GeneratedLoadoutDialog")
        self.setWindowTitle("Generated Loadout")
        self.setMinimumSize(500, 338)
        self.resize(560, 390)

        self.loadout_data = flatten_loadout(copy.deepcopy(loadout_data))
        self.existing_names = {name.casefold() for name in existing_names}
        self.loadout_name = ""

        # Main dialog layout.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # Slim custom header (no close button).
        self.header = CustomDialogHeader("SAVE LOADOUT", self)
        layout.addWidget(self.header)

        # Main content area.
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(17, 12, 17, 17)
        content_layout.setSpacing(10)

        # Loadout name input.
        self.name_input = QLineEdit(self.generate_unique_name())
        self.name_input.setObjectName("generatedLoadoutName")
        self.name_input.selectAll()
        content_layout.addWidget(self.name_input)

        # Loadout preview.
        self.preview_scroll_area = QScrollArea()
        self.preview_scroll_area.setWidgetResizable(True)
        self.preview_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.preview_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.preview_scroll_area.setWidget(
            self._create_loadout_contents(self.loadout_data)
        )
        content_layout.addWidget(self.preview_scroll_area, 1)

        # Bottom action buttons.
        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        confirm = QPushButton("OK")
        confirm.setObjectName("confirm")
        confirm.clicked.connect(self.confirm_loadout)

        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        content_layout.addLayout(buttons)

        layout.addWidget(content, 1)

    def showEvent(self, event):
        super().showEvent(event)

        parent = self.parentWidget()
        if parent is None:
            return

        parent_frame = parent.frameGeometry()
        target_frame_left = parent_frame.left()
        target_frame_top = parent_frame.bottom() + 11

        self.move(target_frame_left, target_frame_top)

    def generate_unique_name(self):
        base = "New Loadout"

        if base.casefold() not in self.existing_names:
            return base

        index = 2

        while f"{base} {index}".casefold() in self.existing_names:
            index += 1

        return f"{base} {index}"

    def confirm_loadout(self):
        name = self.name_input.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Name Required",
                "Please enter a name for this loadout.",
            )
            self.name_input.setFocus()
            return

        if name.casefold() in self.existing_names:
            QMessageBox.warning(
                self,
                "Name Already Exists",
                "A loadout with this name already exists. "
                "Please choose a different name.",
            )
            self.name_input.setFocus()
            self.name_input.selectAll()
            return

        try:
            validate_loadout(name, self.loadout_data)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Invalid Loadout",
                str(exc),
            )
            return

        self.loadout_name = name
        self.accept()
