import re

from PySide6.QtCore import QPropertyAnimation, QRect, QSize, Qt, QTimer
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
    BASE_DIR,
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

LOADOUT_BLOCK_ITEMS = LOADOUT_ITEM_COLUMNS * 2
EXPAND_ITEM_ICON = BASE_DIR / "assets/blank/item_blank.png"
ACTION_SLOT_TEXT = {"expand": "MORE", "shrink": "LESS"}

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
        visible_widths = [
            self._loadout_card_width(name)
            for name in list(reversed(list(self.loadouts)))[:LOADOUTS_MAX_VISIBLE_CARDS]
        ]

        if not visible_widths:
            panel_width = LOADOUTS_EMPTY_PANEL_WIDTH
        else:
            panel_width = (
                sum(visible_widths) + (len(visible_widths) - 1) * LOADOUT_CARD_GAP
            )
            panel_width = max(
                panel_width,
                max(self._loadout_card_width(name) for name in self.loadouts),
            )

        self.loadouts_panel.setFixedWidth(panel_width)
        self.setFixedWidth(WINDOW_FIXED_WIDTH + panel_width)

    def _loadout_card_width(self, name):
        pages = getattr(self, "loadout_pages", {}).get(name, 1)
        return LOADOUT_CARD_WIDTH * pages + LOADOUT_CARD_GAP * (pages - 1)

    def expand_loadout(self, name, step=1):
        """Show the next (or previous) block of items for a loadout card."""
        if not hasattr(self, "loadout_pages"):
            self.loadout_pages = {}
        self.loadout_pages[name] = max(1, self.loadout_pages.get(name, 1) + step)

        scrollbar = self.scroll_area.horizontalScrollBar()
        position = scrollbar.value()
        self.refresh_loadouts()
        scrollbar.setValue(position)

    def _create_loadout_entry(self, name, loadout):

        entry = QWidget()

        entry.setObjectName("loadoutEntry")
        entry.setFixedWidth(self._loadout_card_width(name))

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

        entry_layout.addWidget(
            self._create_loadout_contents(
                loadout,
                max_blocks=getattr(self, "loadout_pages", {}).get(name, 1),
                on_expand=lambda n=name: QTimer.singleShot(
                    0, lambda: self.expand_loadout(n)
                ),
                on_shrink=lambda n=name: QTimer.singleShot(
                    0, lambda: self.expand_loadout(n, -1)
                ),
            ),
            1,
        )

        return entry

    def _create_loadout_contents(
        self, loadout, max_blocks=None, on_expand=None, on_shrink=None
    ):
        """Create a grid of item icons and quantities.

        With max_blocks, items fill blocks of LOADOUT_BLOCK_ITEMS slots laid out
        side by side; the last slot becomes an expand button if items remain.
        """

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
        sorted_items = list(self._sort_loadout_items(loadout))
        display_items = sorted_items

        if max_blocks is not None:
            slot_limit = LOADOUT_BLOCK_ITEMS * max_blocks

            if max_blocks > 1 and len(sorted_items) > LOADOUT_BLOCK_ITEMS:
                # LESS takes a slot; MORE takes the last slot while items remain.
                has_more = len(sorted_items) > slot_limit - 1
                item_slots = slot_limit - 1 - (1 if has_more else 0)
                display_items = sorted_items[:item_slots] + ["shrink"]

                if has_more:
                    display_items.append("expand")
            elif len(sorted_items) > slot_limit:
                display_items = sorted_items[: slot_limit - 1] + ["expand"]

        for column in range(columns * (max_blocks or 1)):
            grid.setColumnStretch(column, 1)
        categories = get_item_categories()
        item_categories = {
            item_name: category
            for category, item_names in categories.items()
            for item_name in item_names
        }
        weapon_names = categories.get("weapons", set())

        for index, display_item in enumerate(display_items):

            is_action_slot = isinstance(display_item, str)
            name, quantity = ("", 0) if is_action_slot else display_item

            if max_blocks is None:
                row_index = index // columns
                column_index = index % columns
            else:
                block, offset = divmod(index, LOADOUT_BLOCK_ITEMS)
                row_index = offset // columns
                column_index = block * columns + offset % columns

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

            if is_action_slot:
                callback = on_expand if display_item == "expand" else on_shrink
                slot.setToolTip(
                    "Show more items"
                    if display_item == "expand"
                    else "Show fewer items"
                )
                slot.setCursor(Qt.CursorShape.PointingHandCursor)
                slot.mousePressEvent = lambda event, callback=callback: callback()
            else:
                slot.setToolTip(get_item_display_name(name))

            slot_layout = QGridLayout(slot)

            slot_layout.setContentsMargins(1, 1, 1, 1)

            slot_layout.setSpacing(0)

            category = item_categories.get(name)
            image_path = None
            if is_action_slot:
                image_path = EXPAND_ITEM_ICON
            elif category is not None:
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

            if not is_action_slot and (
                category not in {"augment", "shields"} or quantity > 1
            ):
                is_weapon = name in weapon_names
                quantity_text = f"×{quantity}"
                if is_weapon:
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

                quantity_anchor = quantity_label

                if is_weapon:
                    # Wrapper with a right margin nudges the weapon tier 3px left.
                    quantity_anchor = QWidget()
                    quantity_anchor.setAttribute(
                        Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                        True,
                    )
                    anchor_layout = QHBoxLayout(quantity_anchor)
                    anchor_layout.setContentsMargins(0, 0, 3, 0)
                    anchor_layout.addWidget(quantity_label)

                slot_layout.addWidget(
                    quantity_anchor,
                    0,
                    0,
                    alignment=(
                        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
                    ),
                )

            if is_action_slot:
                action_label = QLabel(ACTION_SLOT_TEXT[display_item])
                action_label.setObjectName("inventoryAction")
                action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                action_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                    True,
                )
                # The bottom margin shifts the centered text 5px up.
                slot_layout.setContentsMargins(1, 1, 1, 11)
                slot_layout.addWidget(
                    action_label,
                    0,
                    0,
                    alignment=Qt.AlignmentFlag.AlignCenter,
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
