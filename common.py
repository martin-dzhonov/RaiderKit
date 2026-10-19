import json
import logging
import sys
from pathlib import Path
from queue import Empty

from PySide6.QtWidgets import QMessageBox

# BASE_DIR holds bundled read-only resources; DATA_DIR holds user-writable files
# (next to the exe when frozen).
if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR

LOADOUTS_FILE = DATA_DIR / "loadouts.json"
LOADOUT_TAB_OPTIONS_FILE = DATA_DIR / "loadout_tab_options.json"
ITEM_CATEGORIES_FILE = DATA_DIR / "item_categories.json"
ICONS_DIR = BASE_DIR / "assets/icons"
STYLES_FILE = BASE_DIR / "styles.qss"
TEMPLATE_DIR = BASE_DIR / "assets/item_templates"
TEMPLATE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

logger = logging.getLogger(__name__)
_item_categories = None

MAX_WIDGET_SIZE = 16_777_215

# UI sizing
WINDOW_HEIGHT = 274
ACTION_PANEL_BUTTON_WIDTH = 149
ACTION_PANEL_PROGRESS_WIDTH = 135
LOADOUT_CARD_WIDTH = 470
LOADOUT_CARD_GAP = 8
LOADOUTS_EMPTY_PANEL_WIDTH = 200
LOADOUTS_MAX_VISIBLE_CARDS = 3
WINDOW_FIXED_WIDTH = 282
SAVE_STATE_EXTRA_WIDTH = 183
LOADOUT_ITEM_COLUMNS = 6
LOADOUT_ITEM_SLOT_SIZE = 66
LOADOUT_ITEM_SIZE = 64
SCAN_WIDTH = 320
SCAN_HEIGHT = 48
TITLE_BAR_HEIGHT = 34

# Panel sizing
ACTIONS_PANEL_WIDTH = 231

# Inventory sizing
INVENTORY_COLUMNS = 6
INVENTORY_SLOT_SIZE = 50
INVENTORY_ICON_SIZE = 56

ITEM_NAMES = {
    "adrenaline_shot": "Adrenaline Shot",
    "advanced_camera": "Advanced Camera",
    "bandage": "Bandage",
    "barricade_kit": "Barricade Kit",
    "basic_camera": "Basic Camera",
    "binoculars": "Binoculars",
    "blaze_grenade": "Blaze Grenade",
    "blue_light_stick": "Blue Light Stick",
    "combat_mk1": "Combat Mk. 1",
    "combat_mk2": "Combat Mk. 2",
    "combat_mk3": "Combat Mk3",
    "crash_mat": "Crash Mat",
    "deadline": "Deadline",
    "defibrillator": "Defibrillator",
    "dockmasters_detector": "Dockmaster's Detector",
    "door_blocker": "Door Blocker",
    "explosive_mine": "Explosive Mine",
    "firecracker": "Firecracker",
    "fireworks_box": "Fireworks Box",
    "flame_spray": "Flame Spray",
    "gas_grenade": "Gas Grenade",
    "grappling_hook": "Grappling Hook",
    "green_light_stick": "Green Light Stick",
    "heavy_ammo": "Heavy Ammo",
    "heavy_fuze_grenade": "Heavy Fuze Grenade",
    "heavy_shield": "Heavy Shield",
    "herbal_bandage": "Herbal Bandage",
    "jolt_mine": "Jolt Mine",
    "launcher_ammo": "Launcher Ammo",
    "light_ammo": "Light Ammo",
    "light_impact_grenade": "Light Impact Grenade",
    "light_shield": "Light Shield",
    "lil_smoke_grenade": "Li'l Smoke Grenade",
    "looting_mk1": "Looting Mk. 1",
    "looting_mk2": "Looting Mk. 2",
    "looting_mk3": "Looting Mk3",
    "lure_grenade": "Lure Grenade",
    "medium_ammo": "Medium Ammo",
    "medium_shield": "Medium Shield",
    "noisemaker": "Noisemaker",
    "photoelectric_cloak": "Photoelectric Cloak",
    "pulse_mine": "Pulse Mine Blueprint",
    "red_light_stick": "Red Light Stick",
    "remote_raider_flare": "Remote Raider Flare",
    "seeker_grenade": "Seeker Grenade",
    "shield_recharger": "Shield Recharger",
    "shotgun_ammo": "Shotgun Ammo",
    "energy_clip": "Energy Clip",
    "showstopper": "Showstopper",
    "shrapnel_grenade": "Shrapnel Grenade",
    "smoke_grenade": "Smoke Grenade",
    "smoke_grenade_trap": "Smoke Grenade Trap",
    "snap_blast_grenade": "Snap Blast Grenade",
    "snap_hook": "Snap Hook",
    "sterilized_bandage": "Sterilized Bandage",
    "surge_coil": "Surge Coil",
    "surge_shield_recharger": "Surge Shield Recharger",
    "tactical_mk1": "Tactical Mk. 1",
    "tactical_mk2": "Tactical Mk. 2",
    "tactical_mk3": "Tactical Mk3",
    "tagging_grenade": "Tagging Grenade",
    "trailblazer": "Trailblazer",
    "trigger_nade": "Trigger 'Nade",
    "vita_shot": "Vita Shot",
    "vita_spray": "Vita Spray",
    "wolfpack": "Wolfpack",
    "yank_grenade": "Yank Grenade",
    "yellow_light_stick": "Yellow Light Stick",
    "zipline": "Zipline",
    "powered_descender": "Powered Descender",
    "gas_mine": "Gas Mine",
    "blaze_grenade_trap": "Blaze Grenade Trap",
    "lure_grenade_trap": "Lure Grenade Trap",
    "free_loadout": "Free Loadout",
    "tether_launcher": "Tether Launcher",
}


def _read_item_categories():
    data = json.loads(ITEM_CATEGORIES_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("The item category index must contain a JSON object.")

    categories = {}
    for category, item_names in data.items():
        if (
            not isinstance(category, str)
            or not category
            or not isinstance(item_names, list)
            or not all(isinstance(item_name, str) for item_name in item_names)
        ):
            raise ValueError("The item category index has an invalid structure.")
        categories[category] = set(item_names)
    return categories


def refresh_item_categories():
    """Rebuild and persist the item/category index from template assets."""
    global _item_categories

    existing_order = []
    if ITEM_CATEGORIES_FILE.exists():
        try:
            existing_order = list(_read_item_categories())
        except (OSError, json.JSONDecodeError, ValueError):
            logger.warning(
                "Rebuilding invalid item category index: %s",
                ITEM_CATEGORIES_FILE,
                exc_info=True,
            )

    discovered = {}
    for category_dir in TEMPLATE_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        discovered[category_dir.name] = {
            path.stem
            for path in category_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in TEMPLATE_EXTENSIONS
            and path.stem.casefold() != "empty"
        }

    category_order = [category for category in existing_order if category in discovered]
    category_order.extend(sorted(set(discovered).difference(category_order)))
    categories = {category: discovered[category] for category in category_order}
    if not categories:
        raise ValueError(f"No item category folders found in '{TEMPLATE_DIR}'.")

    temporary = ITEM_CATEGORIES_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                category: sorted(item_names)
                for category, item_names in categories.items()
            },
            indent=4,
        ),
        encoding="utf-8",
    )
    temporary.replace(ITEM_CATEGORIES_FILE)
    _item_categories = categories
    return categories


def get_item_categories():
    """Return the cached category index, loading the persisted index if needed."""
    global _item_categories

    if _item_categories is None:
        if ITEM_CATEGORIES_FILE.exists():
            _item_categories = _read_item_categories()
        else:
            return refresh_item_categories()
    return _item_categories


def get_item_display_name(item_key):
    return ITEM_NAMES.get(
        item_key,
        item_key.replace("_", " ").title(),
    )


def load_stylesheet():
    return STYLES_FILE.read_text(encoding="utf-8")


def drain_queue(queue):
    items = []

    while True:
        try:
            items.append(queue.get_nowait())
        except Empty:
            return items


def validate_loadout(name, data):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Please enter a loadout name.")

    if not isinstance(data, dict) or not data:
        raise ValueError("The loadout must contain at least one item.")

    for item, quantity in data.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Item names must be non-empty strings.")

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"Quantity for '{item}' must be a non-negative integer.")


def flatten_loadout(data):
    if not isinstance(data, dict):
        raise ValueError("Each loadout must be a JSON object.")

    if all(
        isinstance(quantity, int) and not isinstance(quantity, bool)
        for quantity in data.values()
    ):
        return dict(data)

    flattened = {}

    for tab, items in data.items():
        if not isinstance(items, dict):
            raise ValueError(f"Tab '{tab}' must contain an object of items.")

        for item, quantity in items.items():
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise ValueError(f"Quantity for '{item}' must be an integer.")

            flattened[item] = flattened.get(item, 0) + quantity

    return flattened


def save_loadouts(loadouts):
    temporary = LOADOUTS_FILE.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(loadouts, indent=4),
        encoding="utf-8",
    )
    temporary.replace(LOADOUTS_FILE)


def save_loadout_tab_options(options):
    temporary = LOADOUT_TAB_OPTIONS_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(options, indent=4),
        encoding="utf-8",
    )
    temporary.replace(LOADOUT_TAB_OPTIONS_FILE)


def read_loadout_tab_options(loadout_names):
    category_names = get_item_categories()
    options = {
        name: {category: True for category in category_names} for name in loadout_names
    }
    if not LOADOUT_TAB_OPTIONS_FILE.exists():
        return options

    try:
        stored_options = json.loads(
            LOADOUT_TAB_OPTIONS_FILE.read_text(encoding="utf-8")
        )
        if not isinstance(stored_options, dict):
            raise ValueError("The file must contain a JSON object.")

        loaded_options = {}
        for name in options:
            saved = stored_options.get(name, {})
            if not isinstance(saved, dict):
                raise ValueError(f"Options for '{name}' must be a JSON object.")
            loaded_options[name] = {}
            for category in category_names:
                if category == "shields":
                    value = saved.get(
                        "shields",
                        saved.get("augment_shields", True),
                    )
                else:
                    value = saved.get(category, True)
                if not isinstance(value, bool):
                    raise ValueError(
                        f"Option '{category}' for '{name}' must be true or false."
                    )
                loaded_options[name][category] = value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        QMessageBox.warning(
            None,
            "Loadout Options",
            f"Could not read loadout_tab_options.json:\n{exc}\n\n"
            "All equip tabs will be enabled by default.",
        )
    else:
        options = loaded_options

    return options


def read_loadouts():
    if not LOADOUTS_FILE.exists():
        return {}

    try:
        data = json.loads(LOADOUTS_FILE.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            raise ValueError("The file must contain a JSON object.")

        loadouts = {}
        migrated = False

        for name, items in data.items():
            flattened = flatten_loadout(items)
            validate_loadout(name, flattened)

            loadouts[name] = flattened
            migrated |= flattened != items

        if migrated:
            save_loadouts(loadouts)

        return loadouts

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        QMessageBox.warning(
            None,
            "Loadouts",
            f"Could not read loadouts.json:\n{exc}\n\n"
            "Starting with an empty loadout list.",
        )
        return {}
