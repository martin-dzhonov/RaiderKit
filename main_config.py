# main_config.py

GRID_CONFIGS = {
    "stash": {
        "scan_x": 289,
        "start_y": 350,
        "bottom_y": 1260,
        "item_width": 128,
        "item_height": 128,
        "icon_height": 96,
        "column_x": (203, 341, 480, 619),
        "banner_height": 30,
        "banner_width": 40,
    },
    "player_main": {
        "scan_x": 1438,
        "start_y": 345,
        "bottom_y": 1190,
        "item_width": 128,
        "item_height": 128,
        "icon_height": 96,
        "column_x": (1392, 1531, 1669, 1808),
        "banner_height": 30,
        "banner_width": 40,
    },
    "player_quickuse": {
        "scan_x": 2095,
        "start_y": 345,
        "bottom_y": 635,
        "item_width": 128,
        "item_height": 128,
        "icon_height": 96,
        "column_x": (2005, 2144, 2283),
        "banner_height": 30,
        "banner_width": 40,
    },
    "player_augmented": {
        "scan_x": 2095,
        "start_y": 715,
        "bottom_y": 860,
        "item_width": 128,
        "item_height": 128,
        "icon_height": 96,
        "column_x": (2005, 2144, 2283),
        "banner_height": 30,
        "banner_width": 40,
    },
}
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

# Default grid configuration
SCAN_X = GRID_CONFIGS["stash"]["scan_x"]
SCAN_START_Y = GRID_CONFIGS["stash"]["start_y"]
BOTTOM_SCAN_Y = GRID_CONFIGS["stash"]["bottom_y"]
ITEM_HEIGHT = GRID_CONFIGS["stash"]["item_height"]


# Grid detection
BORDER_WIDTH = 2
MIN_BORDER_DISTANCE = 4
BORDER_HEIGHT_TOLERANCE = 4

BANNER_COLOR = (9, 12, 25)
BANNER_HEIGHT = 30

ROW_BORDER_MAX_RUN = 5
ROW_BANNER_MIN_RUN = 2


# Scrollbar detection
SCROLLBAR_X = 780
SCROLLBAR_START_Y = 350
SCROLLBAR_END_Y = 1275

SCROLLBAR_COLOR = (96, 102, 118)
SCROLLBAR_HIGHLIGHT_COLOR = (164, 165, 170)

SCROLLBAR_COLORS = (
    SCROLLBAR_COLOR,
    SCROLLBAR_HIGHLIGHT_COLOR,
)

# Scrolling behavior
SCROLL_SETTLE_DELAY = 0.20
