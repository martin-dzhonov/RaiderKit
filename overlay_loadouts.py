from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from common import (
    TAB_ITEMS,
    TEMPLATE_DIR,
    get_item_display_name,
)


class OverlayLoadoutsMixin:

    LOADOUT_CARD_WIDTH = 470
    LOADOUT_ITEM_SLOT_SIZE = 66
    LOADOUT_ITEM_ICON_SIZE = 64

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
        weapon_names = {
            path.stem for path in TEMPLATE_DIR.glob("weapons/*") if path.is_file()
        }
        for weapon_name in weapon_names:
            item_tab[weapon_name] = "weapons"

        return sorted(
            loadout.items(),
            key=lambda item: tab_priority.get(
                item_tab.get(item[0]),
                len(tab_priority),
            ),
        )

    def refresh_loadouts(self):

        while self.loadout_list.count():

            item = self.loadout_list.takeAt(0)

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        if not self.loadouts:

            empty = QLabel("No loadouts yet.")

            empty.setObjectName("hint")

            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

            empty.setWordWrap(True)

            self.loadout_list.addWidget(empty)

        else:

            for name, loadout in reversed(list(self.loadouts.items())):

                self.loadout_list.addWidget(self._create_loadout_entry(name, loadout))

        self.loadout_list.addStretch(1)

    def _create_loadout_entry(self, name, loadout):

        entry = QWidget()

        entry.setObjectName("loadoutEntry")
        entry.setFixedWidth(self.LOADOUT_CARD_WIDTH)

        entry_layout = QVBoxLayout(entry)

        entry_layout.setContentsMargins(8, 8, 8, 3)

        entry_layout.setSpacing(4)

        row = QWidget()

        row.setObjectName("loadoutRow")

        row_layout = QHBoxLayout(row)

        row_layout.setContentsMargins(0, 0, 0, 0)

        row_layout.setSpacing(6)

        label = QLabel(name)

        label.setObjectName("loadoutName")

        label.setContentsMargins(12, 0, 0, 0)

        label.setWordWrap(True)

        delete = QPushButton("X")

        delete.setObjectName("quit")

        delete.setFixedSize(28, 28)

        delete.clicked.connect(
            lambda checked=False, n=name: self.delete_loadout_operation(self, n)
        )

        load = QPushButton("Equip")

        load.setObjectName("scan")

        load.setFixedWidth(64)

        load.setEnabled(self.initialization_complete)

        load.clicked.connect(lambda checked=False, n=name: self.load_loadout(n))

        row_layout.addWidget(label, 1)

        row_layout.addWidget(delete)

        row_layout.addWidget(load)

        entry_layout.addWidget(row)

        entry_layout.addWidget(self._create_loadout_contents(loadout), 1)

        return entry

    def _create_loadout_contents(self, loadout):
        """Create a grid of item icons and quantities."""

        contents = QWidget()

        contents.setObjectName("loadoutContents")

        grid = QGridLayout(contents)

        grid.setContentsMargins(8, 4, 8, 4)

        grid.setHorizontalSpacing(7)

        grid.setVerticalSpacing(8)

        grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        if not loadout:

            empty = QLabel("This loadout is empty.")

            empty.setObjectName("hint")

            grid.addWidget(empty, 0, 0)

            return contents

        columns = 6

        for index, (name, quantity) in enumerate(self._sort_loadout_items(loadout)):

            row_index = index // columns

            column_index = index % columns

            item_widget = QWidget()

            item_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )

            item_widget.setFixedWidth(self.LOADOUT_ITEM_SLOT_SIZE)

            item_layout = QVBoxLayout(item_widget)

            item_layout.setContentsMargins(0, 0, 0, 0)

            item_layout.setSpacing(0)

            slot = QFrame()

            slot.setObjectName("inventorySlot")

            slot.setFixedSize(
                self.LOADOUT_ITEM_SLOT_SIZE,
                self.LOADOUT_ITEM_SLOT_SIZE,
            )

            slot.setToolTip(get_item_display_name(name))

            slot_layout = QGridLayout(slot)

            slot_layout.setContentsMargins(1, 1, 1, 1)

            slot_layout.setSpacing(0)

            image_path = next(
                (
                    path
                    for extension in ("webp", "png")
                    for path in sorted(TEMPLATE_DIR.glob(f"*/{name}.{extension}"))
                ),
                None,
            )

            if image_path is not None:

                pixmap = QPixmap(str(image_path))

                if not pixmap.isNull():
                    icon_label = QLabel()

                    icon_label.setObjectName("inventoryIcon")

                    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

                    icon_label.setFixedSize(
                        self.LOADOUT_ITEM_ICON_SIZE,
                        self.LOADOUT_ITEM_ICON_SIZE,
                    )

                    icon_label.setPixmap(
                        pixmap.scaled(
                            self.LOADOUT_ITEM_ICON_SIZE,
                            self.LOADOUT_ITEM_ICON_SIZE,
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

            is_weapon = name in TAB_ITEMS.get("weapons", set()) or (
                image_path is not None
                and image_path.parent.name.casefold() == "weapons"
            )

            if is_weapon:
                display_name = get_item_display_name(name)

                name_label = QLabel(display_name)

                name_label.setObjectName("inventoryItemName")

                name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

                name_label.setWordWrap(True)

                name_label.setToolTip(display_name)

                name_label.setFixedWidth(self.LOADOUT_ITEM_SLOT_SIZE)

            item_widget.adjustSize()

            grid.addWidget(
                item_widget,
                row_index,
                column_index,
                alignment=(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            )

        return contents
