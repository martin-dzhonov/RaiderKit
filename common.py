import json
from pathlib import Path
from queue import Empty

from PySide6.QtWidgets import QMessageBox

BASE_DIR = Path(__file__).resolve().parent

LOADOUTS_FILE = BASE_DIR / "loadouts.json"
STYLES_FILE = BASE_DIR / "styles.qss"
TEMPLATE_DIR = BASE_DIR / "item_templates"

MAX_WIDGET_SIZE = 16_777_215

# Window sizing
NORMAL_HEIGHT = 276
SCAN_WIDTH = 320
SCAN_HEIGHT = 48
TITLE_BAR_HEIGHT = 34

# Independently configurable panel widths
ACTIONS_PANEL_WIDTH = 145
LOADOUTS_PANEL_WIDTH = 430
DETAILS_WIDTH = 420

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
}


TAB_ITEMS = {
    "augment": {
        "combat_mk1",
        "combat_mk2",
        "combat_mk3",
        "looting_mk1",
        "looting_mk2",
        "looting_mk3",
        "tactical_mk1",
        "tactical_mk2",
        "tactical_mk3",
    },
    "shields": {"heavy_shield", "light_shield", "medium_shield"},
    "weapons": {"stg"},
    "ammo": {
        "energy_clip",
        "heavy_ammo",
        "launcher_ammo",
        "light_ammo",
        "medium_ammo",
        "shotgun_ammo",
    },
    "quickuse": {
        "adrenaline_shot",
        "advanced_camera",
        "bandage",
        "barricade_kit",
        "basic_camera",
        "binoculars",
        "blaze_grenade",
        "blue_light_stick",
        "crash_mat",
        "deadline",
        "defibrillator",
        "dockmasters_detector",
        "door_blocker",
        "explosive_mine",
        "firecracker",
        "fireworks_box",
        "flame_spray",
        "gas_grenade",
        "grappling_hook",
        "green_light_stick",
        "heavy_fuze_grenade",
        "herbal_bandage",
        "jolt_mine",
        "light_impact_grenade",
        "lil_smoke_grenade",
        "lure_grenade",
        "noisemaker",
        "photoelectric_cloak",
        "pulse_mine",
        "red_light_stick",
        "remote_raider_flare",
        "seeker_grenade",
        "shield_recharger",
        "showstopper",
        "shrapnel_grenade",
        "smoke_grenade",
        "smoke_grenade_trap",
        "snap_blast_grenade",
        "snap_hook",
        "sterilized_bandage",
        "surge_coil",
        "surge_shield_recharger",
        "tagging_grenade",
        "trailblazer",
        "trigger_nade",
        "vita_shot",
        "vita_spray",
        "wolfpack",
        "yank_grenade",
        "yellow_light_stick",
        "zipline",
    },
}


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
