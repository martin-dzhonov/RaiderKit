import re

from PySide6.QtCore import QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)
from common import (
    ICONS_DIR,
    LOADOUT_CARD_WIDTH,
    LOADOUT_CARD_GAP,
    LOADOUT_ITEM_COLUMNS,
    LOADOUT_ITEM_SLOT_SIZE,
    LOADOUT_ITEM_SIZE,
    LOADOUTS_EMPTY_PANEL_WIDTH,
    LOADOUTS_MAX_VISIBLE_CARDS,
    TEMPLATE_DIR,
    WINDOW_FIXED_WIDTH,
    get_item_categories,
    get_item_display_name,
)

CATEGORY_PRESENTATION = {
    "augment": ("Augment", "Icon_Augment.png"),
    "shields": ("Shields", "Icon_Shield.png"),
    "weapons": ("Weapons", "Icon_Weapon.png"),
    "ammo": ("Ammo", "Icon_Ammo.png"),
    "quickuse": ("Quick Use", "Icon_Quick_Use.png"),
}


class CategoryCheckBox(QCheckBox):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.drawRoundedRect(self.rect(), 4, 4)

        icon_rect = QRect(4, 8, 24, 20)
        self.icon().paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

        painter.setPen(QPen(QColor("#191e2d"), 1.5))
        painter.setBrush(QColor("#6df5c4" if self.isChecked() else "#ff6b81"))
        painter.drawEllipse(icon_rect.right() - 5, icon_rect.bottom() - 5, 8, 8)


class OverlayLoadoutsMixin:

    def set_loadout_equip_progress(self, active_name):
        for name, progress_bar in self.loadout_equip_progress_bars.items():
            animation = self.loadout_equip_animations[name]
            animation.stop()
            progress_bar.setValue(0)
            progress_bar.setVisible(name == active_name)

            if name == active_name:
                animation.start()

    def _sort_loadout_items(self, loadout):
        """Sort items by tab priority, preserving order within each tab."""

        categories = get_item_categories()
        tab_priority = {
            category: priority for priority, category in enumerate(categories)
        }
        item_tab = {
            item_name: category
            for category, items in categories.items()
            for item_name in items
        }

        return sorted(
            loadout.items(),
            key=lambda item: tab_priority.get(
                item_tab.get(item[0]),
                len(tab_priority),
            ),
        )

    def refresh_loadouts(self):
        if hasattr(self, "loadout_equip_animations"):
            for animation in self.loadout_equip_animations.values():
                animation.stop()
            self.loadout_equip_progress_bars.clear()
            self.loadout_equip_animations.clear()

        while self.loadout_list.count():

            item = self.loadout_list.takeAt(0)

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        if not self.loadouts:

            empty_state = QWidget()
            empty_state.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )

            empty_state_layout = QVBoxLayout(empty_state)
            empty_state_layout.setContentsMargins(0, 0, 0, 0)
            empty_state_layout.setSpacing(0)
            empty_state_layout.addStretch(1)

            empty = QLabel("NO LOADOUTS\nYET")
            empty.setObjectName("emptyLoadoutsMessage")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty_state_layout.addWidget(empty)
            empty_state_layout.addSpacing(60)
            empty_state_layout.addStretch(1)

            self.loadout_list.addWidget(empty_state, 1)

        else:

            for name, loadout in reversed(list(self.loadouts.items())):
                self.loadout_tab_options.setdefault(
                    name,
                    {category: True for category in get_item_categories()},
                )

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

        entry_layout.setContentsMargins(0, 0, 0, 3)

        entry_layout.setSpacing(4)

        row = QWidget()
        row.setObjectName("loadoutRow")
        row.setFixedHeight(37)
        row_stack = QStackedLayout(row)
        row_stack.setContentsMargins(0, 0, 0, 0)
        row_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        progress_bar = QProgressBar(row)
        progress_bar.setObjectName("loadoutEquipProgress")
        progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        progress_bar.setRange(0, 1000)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        progress_bar.hide()
        row_stack.addWidget(progress_bar)

        content = QWidget(row)
        content.setObjectName("loadoutRowContent")
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        content.setAutoFillBackground(False)
        row_layout = QHBoxLayout(content)

        row_layout.setContentsMargins(0, 0, 0, 0)

        row_layout.setSpacing(6)

        title = f"{name[:23]}.." if len(name) > 23 else name
        label = QLabel(title)

        label.setObjectName("loadoutName")

        label.setContentsMargins(12, 0, 0, 0)

        label.setToolTip(name)
        label.setWordWrap(False)

        delete = QPushButton()

        delete.setObjectName("quit")

        delete.setFixedSize(26, 32)
        delete.setAccessibleName("Delete loadout")
        delete.setToolTip("Delete loadout")
        delete.setIcon(QIcon(str(ICONS_DIR / "trash-bin.png")))
        delete.setIconSize(QSize(23, 23))

        delete.clicked.connect(
            lambda checked=False, n=name: self.delete_loadout_operation(self, n)
        )

        load = QPushButton("Equip")

        load.setObjectName("scan")

        load.setFixedSize(64, 37)

        load.setEnabled(self.initialization_complete)

        load.clicked.connect(lambda checked=False, n=name: self.load_loadout(n))

        row_layout.addWidget(label)
        row_layout.addWidget(delete)
        row_layout.addStretch(1)

        for category in get_item_categories():
            label_text, icon_name = CATEGORY_PRESENTATION.get(
                category,
                (category.replace("_", " ").title(), ""),
            )
            checkbox = CategoryCheckBox()
            checkbox.setObjectName("loadoutTabOption")
            checkbox.setAccessibleName(label_text)
            checkbox.setToolTip(label_text)
            if icon_name:
                checkbox.setIcon(QIcon(str(ICONS_DIR / icon_name)))
            checkbox.setIconSize(QSize(26, 26))
            checkbox.setFixedSize(32, 37)
            checkbox.setChecked(self.loadout_tab_options[name][category])
            checkbox.toggled.connect(
                lambda enabled, n=name, c=category: self.update_loadout_tab_option(
                    n,
                    c,
                    enabled,
                )
            )
            row_layout.addWidget(checkbox)

        row_layout.addSpacing(6)
        row_layout.addWidget(load)

        row_stack.addWidget(content)
        progress_bar.lower()
        entry_layout.addWidget(row)

        if not hasattr(self, "loadout_equip_progress_bars"):
            self.loadout_equip_progress_bars = {}
            self.loadout_equip_animations = {}
        self.loadout_equip_progress_bars[name] = progress_bar
        animation = QPropertyAnimation(progress_bar, b"value", progress_bar)
        animation.setStartValue(0)
        animation.setEndValue(1000)
        animation.setDuration(2000)
        animation.setLoopCount(-1)
        self.loadout_equip_animations[name] = animation

        entry_layout.addWidget(self._create_loadout_contents(loadout), 1)

        return entry

    def _create_loadout_contents(self, loadout):
        """Create a grid of item icons and quantities."""

        contents = QWidget()

        contents.setObjectName("loadoutContents")

        grid = QGridLayout(contents)

        grid.setContentsMargins(8, 9, 8, 4)

        grid.setHorizontalSpacing(7)

        grid.setVerticalSpacing(8)

        grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        if not loadout:

            empty = QLabel("This loadout is empty.")

            empty.setObjectName("hint")

            grid.addWidget(empty, 0, 0)

            return contents

        columns = LOADOUT_ITEM_COLUMNS

        # Reserve every column so short grids keep the same slot positions as full ones.
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        categories = get_item_categories()
        item_categories = {
            item_name: category
            for category, item_names in categories.items()
            for item_name in item_names
        }
        weapon_names = categories.get("weapons", set())

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

            category = item_categories.get(name)
            image_path = None
            if category is not None:
                for extension in ("webp", "png"):
                    candidate = TEMPLATE_DIR / category / f"{name}.{extension}"
                    if candidate.is_file():
                        image_path = candidate
                        break

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

            if category not in {"augment", "shields"} or quantity > 1:
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
