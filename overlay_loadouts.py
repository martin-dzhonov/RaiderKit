import re

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
    LOADOUT_CARD_WIDTH,
    LOADOUT_CARD_GAP,
    LOADOUT_ITEM_COLUMNS,
    LOADOUT_ITEM_SLOT_SIZE,
    LOADOUT_ITEM_SIZE,
    LOADOUTS_EMPTY_PANEL_WIDTH,
    LOADOUTS_MAX_VISIBLE_CARDS,
    TAB_ITEMS,
    TEMPLATE_DIR,
    WINDOW_FIXED_WIDTH,
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

            empty = QLabel("NO LOADOUTS\nYET")

            empty.setObjectName("emptyLoadoutsMessage")

            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

            empty.setWordWrap(True)

            empty.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )

            self.loadout_list.addWidget(empty, 1)

        else:

            for name, loadout in reversed(list(self.loadouts.items())):

                self.loadout_list.addWidget(self._create_loadout_entry(name, loadout))

        if self.loadouts:
            self.loadout_list.addStretch(1)
        self._resize_for_loadout_count()

    def _resize_for_loadout_count(self):
        visible_count = min(len(self.loadouts), LOADOUTS_MAX_VISIBLE_CARDS)

        if visible_count == 0:
            panel_width = LOADOUTS_EMPTY_PANEL_WIDTH
        else:
            panel_width = (
                visible_count * LOADOUT_CARD_WIDTH
                + (visible_count - 1) * LOADOUT_CARD_GAP
            )

        self.loadouts_panel.setFixedWidth(panel_width)
        self.setFixedWidth(WINDOW_FIXED_WIDTH + panel_width)

    def _create_loadout_entry(self, name, loadout):

        entry = QWidget()

        entry.setObjectName("loadoutEntry")
        entry.setFixedWidth(LOADOUT_CARD_WIDTH)

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

        columns = LOADOUT_ITEM_COLUMNS
        weapon_names = {
            path.stem for path in TEMPLATE_DIR.glob("weapons/*") if path.is_file()
        }

        for index, (name, quantity) in enumerate(self._sort_loadout_items(loadout)):

            row_index = index // columns

            column_index = index % columns

            item_widget = QWidget()

            item_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )

            item_widget.setFixedWidth(LOADOUT_ITEM_SLOT_SIZE)

            item_layout = QVBoxLayout(item_widget)

            item_layout.setContentsMargins(0, 0, 0, 0)

            item_layout.setSpacing(0)

            slot = QFrame()

            slot.setObjectName("inventorySlot")

            slot.setFixedSize(
                LOADOUT_ITEM_SLOT_SIZE,
                LOADOUT_ITEM_SLOT_SIZE,
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
                        LOADOUT_ITEM_SIZE,
                        LOADOUT_ITEM_SIZE,
                    )

                    icon_label.setPixmap(
                        pixmap.scaled(
                            LOADOUT_ITEM_SIZE,
                            LOADOUT_ITEM_SIZE,
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

            if name not in TAB_ITEMS["augment"] and name not in TAB_ITEMS["shields"]:
                quantity_text = f"×{quantity}"
                if name in weapon_names:
                    weapon_tier = re.search(r"([IVXLCDM]+)_\d+$", name, re.IGNORECASE)
                    if weapon_tier is not None:
                        quantity_text = weapon_tier.group(1)

                quantity_label = QLabel(quantity_text)

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
                    alignment=(
                        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
                    ),
                )

            item_layout.addWidget(
                slot,
                alignment=Qt.AlignmentFlag.AlignHCenter,
            )

            item_widget.adjustSize()

            grid.addWidget(
                item_widget,
                row_index,
                column_index,
                alignment=(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            )

        return contents
