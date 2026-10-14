import copy
import json

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from common import flatten_loadout, validate_loadout


class GeneratedLoadoutDialog(QDialog):
    def __init__(self, loadout_data, existing_names, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Generated Loadout")
        self.setMinimumSize(500, 520)
        self.resize(560, 600)

        self.loadout_data = flatten_loadout(copy.deepcopy(loadout_data))
        self.existing_names = {name.casefold() for name in existing_names}
        self.loadout_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("SAVE LOADOUT")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Loadout name:"))

        self.name_input = QLineEdit(self.generate_unique_name())
        self.name_input.selectAll()
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Generated JSON preview:"))

        self.json_preview = QPlainTextEdit()
        self.json_preview.setReadOnly(True)
        self.json_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.json_preview.setPlainText(json.dumps(self.loadout_data, indent=4))
        layout.addWidget(self.json_preview, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        confirm = QPushButton("OK")
        confirm.setObjectName("confirm")
        confirm.clicked.connect(self.confirm_loadout)

        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

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
