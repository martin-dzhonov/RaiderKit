from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

items = [
    "adrenaline_shot",
    "advanced_camera",
    "bandage",
    "barricade_kit",
    "basic_camera",
    "binoculars",
    "blaze_grenade",
    "blue_light_stick",
    "combat_mk1",
    "combat_mk2",
    "combat_mk3_aggressive",
    "looting_mk3_cautious",
    "tactical_mk3_defensive",
    "crash_mat",
    "deadline",
    "defibrillator",
    "dockmasters_detector",
    "door_blocker",
    "jump_mine",
    "firecracker",
    "fireworks_box",
    "flame_spray",
    "gas_grenade",
    "grappling_hook",
    "green_light_stick",
    "heavy_ammo",
    "heavy_fuze_grenade",
    "heavy_shield",
    "herbal_bandage",
    "jolt_mine",
    "launcher_ammo",
    "light_ammo",
    "light_impact_grenade",
    "light_shield",
    "lil_smoke_grenade",
    "looting_mk1",
    "looting_mk2",
    "looting_mk3",
    "lure_grenade",
    "medium_ammo",
    "medium_shield",
    "noisemaker",
    "photoelectric_cloak",
    "pulse_mine",
    "red_light_stick",
    "remote_raider_flare",
    "seeker_grenade",
    "shield_recharger",
    "shotgun_ammo",
    "showstopper",
    "shrapnel_grenade",
    "smoke_grenade",
    "smoke_grenade_trap",
    "snap_blast_grenade",
    "snap_hook",
    "sterilized_bandage",
    "surge_coil",
    "surge_shield_recharger",
    "tactical_mk1",
    "tactical_mk2",
    "tactical_mk3",
    "tagging_grenade",
    "trailblazer",
    "trigger_nade",
    "vita_shot",
    "vita_spray",
    "wolfpack",
    "yank_grenade",
    "yellow_light_stick",
    "zipline",
    "recipe",
]

BASE_URL = "https://ardb.app/static/items/icons/{}.webp"
OUTPUT_DIR = Path("item_icons")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

success = 0
failed = []

for item in items:
    url = BASE_URL.format(item)
    output_file = OUTPUT_DIR / f"{item}.webp"

    try:
        with urlopen(url, timeout=20) as response:
            image_data = response.read()

        output_file.write_bytes(image_data)
        success += 1
        print(f"[OK] {item}.webp")

    except (HTTPError, URLError, TimeoutError, OSError) as e:
        failed.append(item)
        print(f"[FAILED] {item}: {e}")

print(f"\nFinished! Downloaded {success}/{len(items)} icons.")
print(f"Folder: {OUTPUT_DIR.resolve()}")

if failed:
    print("\nFailed items:")
    print(", ".join(failed))
