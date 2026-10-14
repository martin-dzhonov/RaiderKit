from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from common import (
    INVENTORY_COLUMNS,
    INVENTORY_ICON_SIZE,
    INVENTORY_SLOT_SIZE,
    ITEM_ICONS_DIR,
    ITEM_NAMES,
    TAB_ITEMS,
    get_item_display_name,
)


class OverlayLoadoutsMixin:

    def _sort_loadout_items(self, loadout):
        """Sort items by tab priority, preserving order within each tab."""

        tab_priority = {
            "augment": 0,
            "shields": 1,
            "weapons": 2,
            "ammo": 3,
            "quickuse": 4,
        }

        item_tab = {
            item_name: tab for tab, items in TAB_ITEMS.items() for item_name in items
        }

        return sorted(
            loadout.items(),
            key=lambda item: tab_priority.get(
                item_tab.get(item[0]),
                len(tab_priority),
            ),
        )

    def _clear_details_content(self):

        while self.details_content_layout.count():

            item = self.details_content_layout.takeAt(0)

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

    def show_loadout_details(self, name):

        if name not in self.loadouts:

            self.hide_loadout_details()

            return

        self.details_open = True

        self.selected_loadout_name = name

        self.details_loadout_name.setText(f"- {name}")

        self.details_loadout_name.setToolTip(name)

        self._clear_details_content()

        contents = self._create_loadout_contents(self.loadouts[name])

        self.details_content_layout.addWidget(contents)

        self.details_content_layout.addStretch(1)

        self.details_panel.setMinimumWidth(self.details_width)

        self.details_panel.setMaximumWidth(self.details_width)

        self.details_panel.show()

        self.normal_width = self.calculate_window_width(details=False)

        self.expanded_width = self.calculate_window_width(details=True)

        self._resize_window(self.expanded_width)

    def hide_loadout_details(self):

        self.details_open = False

        self.selected_loadout_name = None

        self.details_loadout_name.setText("")

        self.details_panel.hide()

        self.details_panel.setMinimumWidth(0)

        self.details_panel.setMaximumWidth(0)

        self._clear_details_content()

        self.normal_width = self.calculate_window_width(details=False)

        self.expanded_width = self.calculate_window_width(details=True)

        self._resize_window(self.normal_width)

    def refresh_loadouts(self):

        while self.loadout_list.count():

            item = self.loadout_list.takeAt(0)

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        self.loadout_expand_buttons = {}

        if not self.loadouts:

            empty = QLabel("No loadouts yet.")

            empty.setObjectName("hint")

            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

            empty.setWordWrap(True)

            self.loadout_list.addWidget(empty)

        else:

            for name, loadout in reversed(list(self.loadouts.items())):

                self.loadout_list.addWidget(self._create_loadout_entry(name, loadout))

        self.loadout_list.addStretch()

        if self.details_open:

            if self.selected_loadout_name in self.loadouts:

                button = self.loadout_expand_buttons.get(self.selected_loadout_name)

                if button is not None:

                    button.blockSignals(True)

                    button.setChecked(True)

                    button.setText("Viewing")

                    button.blockSignals(False)

                self.show_loadout_details(self.selected_loadout_name)

            else:

                self.hide_loadout_details()

    def _create_loadout_entry(self, name, loadout):

        entry = QWidget()

        entry.setObjectName("loadoutEntry")

        entry_layout = QVBoxLayout(entry)

        entry_layout.setContentsMargins(0, 0, 0, 0)

        entry_layout.setSpacing(0)

        row = QWidget()

        row.setObjectName("loadoutRow")

        row_layout = QHBoxLayout(row)

        row_layout.setContentsMargins(8, 8, 8, 8)

        row_layout.setSpacing(6)

        label = QLabel(name)

        label.setObjectName("loadoutName")

        label.setWordWrap(True)

        delete = QPushButton("X")

        delete.setObjectName("quit")

        delete.setFixedWidth(32)

        delete.clicked.connect(
            lambda checked=False, n=name: self.delete_loadout_operation(self, n)
        )

        expand = QPushButton("View")

        expand.setObjectName("loadoutExpand")

        expand.setFixedWidth(75)

        expand.setCheckable(True)

        expand.setToolTip("Show or hide loadout contents")

        expand.setProperty("loadout_name", name)

        if self.details_open and self.selected_loadout_name == name:

            expand.setChecked(True)

            expand.setText("Viewing")

        self.loadout_expand_buttons[name] = expand

        load = QPushButton("Equip")

        load.setObjectName("scan")

        load.setFixedWidth(64)

        load.setEnabled(self.initialization_complete)

        load.clicked.connect(lambda checked=False, n=name: self.load_loadout(n))

        row_layout.addWidget(label, 1)

        row_layout.addWidget(delete)

        row_layout.addWidget(expand)

        row_layout.addWidget(load)

        entry_layout.addWidget(row)

        expand.toggled.connect(
            lambda checked, n=name: self._on_loadout_arrow_toggled(n, checked)
        )

        return entry

    def _on_loadout_arrow_toggled(self, name, checked):

        if checked:

            for other_name, button in self.loadout_expand_buttons.items():

                if other_name != name and button.isChecked():

                    button.blockSignals(True)

                    button.setChecked(False)

                    button.setText("View")

                    button.blockSignals(False)

            self.show_loadout_details(name)

        elif self.selected_loadout_name == name:

            self.hide_loadout_details()

        sender_button = self.loadout_expand_buttons.get(name)

        if sender_button is not None:

            sender_button.setText("Viewing" if checked else "View")

    def _create_loadout_contents(self, loadout):
        """Create a fixed-width grid of item icons and quantities."""

        contents = QWidget()

        contents.setObjectName("loadoutContents")

        grid = QGridLayout(contents)

        grid.setContentsMargins(8, 4, 8, 4)

        grid.setHorizontalSpacing(7)

        grid.setVerticalSpacing(4)

        grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        if not loadout:

            empty = QLabel("This loadout is empty.")

            empty.setObjectName("hint")

            grid.addWidget(empty, 0, 0)

            return contents

        for index, (name, quantity) in enumerate(self._sort_loadout_items(loadout)):

            row_index = index // INVENTORY_COLUMNS

            column_index = index % INVENTORY_COLUMNS

            item_widget = QWidget()

            item_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )

            item_widget.setFixedWidth(INVENTORY_SLOT_SIZE)

            item_layout = QVBoxLayout(item_widget)

            item_layout.setContentsMargins(0, 0, 0, 0)

            item_layout.setSpacing(0)

            slot = QFrame()

            slot.setObjectName("inventorySlot")

            slot.setFixedSize(
                INVENTORY_SLOT_SIZE,
                INVENTORY_SLOT_SIZE,
            )

            slot.setToolTip(get_item_display_name(name))

            slot_layout = QGridLayout(slot)

            slot_layout.setContentsMargins(3, 3, 3, 3)

            slot_layout.setSpacing(0)

            image_path = ITEM_ICONS_DIR / f"{name}.webp"

            if not image_path.is_file():

                image_path = ITEM_ICONS_DIR / f"{name}.png"

            if image_path.is_file():

                pixmap = QPixmap(str(image_path))

                if not pixmap.isNull():

                    icon_label = QLabel()

                    icon_label.setObjectName("inventoryIcon")

                    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

                    icon_label.setFixedSize(
                        INVENTORY_ICON_SIZE,
                        INVENTORY_ICON_SIZE,
                    )

                    icon_label.setPixmap(
                        pixmap.scaled(
                            INVENTORY_ICON_SIZE,
                            INVENTORY_ICON_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )

                    slot_layout.addWidget(
                        icon_label,
                        0,
                        0,
                        alignment=Qt.AlignmentFlag.AlignCenter,
                    )

            quantity_label = QLabel(f"×{quantity}")

            quantity_label.setObjectName("inventoryQuantity")

            quantity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            quantity_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )

            slot_layout.addWidget(
                quantity_label,
                0,
                0,
                alignment=(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight),
            )

            item_layout.addWidget(
                slot,
                alignment=Qt.AlignmentFlag.AlignHCenter,
            )

            display_name = get_item_display_name(name)

            name_label = QLabel(display_name)

            name_label.setObjectName("inventoryItemName")

            name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            name_label.setWordWrap(True)

            name_label.setToolTip(display_name)

            name_label.setFixedWidth(INVENTORY_SLOT_SIZE)

            item_layout.addWidget(name_label)

            item_widget.adjustSize()

            grid.addWidget(
                item_widget,
                row_index,
                column_index,
                alignment=(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            )

        return contents
