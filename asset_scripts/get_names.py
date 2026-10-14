import requests
import json
import re

item_ids = """
adrenaline_shot, advanced_camera, bandage, barricade_kit,
basic_camera, binoculars, blaze_grenade, blue_light_stick,
combat_mk1, combat_mk2, combat_mk3, crash_mat, deadline,
defibrillator, dockmasters_detector, door_blocker,
explosive_mine, firecracker, fireworks_box, flame_spray,
gas_grenade, grappling_hook, green_light_stick, heavy_ammo,
heavy_fuze_grenade, heavy_shield, herbal_bandage, jolt_mine,
launcher_ammo, light_ammo, light_impact_grenade, light_shield,
lil_smoke_grenade, looting_mk1, looting_mk2, looting_mk3,
lure_grenade, medium_ammo, medium_shield, noisemaker,
photoelectric_cloak, pulse_mine, red_light_stick,
remote_raider_flare, seeker_grenade, shield_recharger,
shotgun_ammo, showstopper, shrapnel_grenade, smoke_grenade,
smoke_grenade_trap, snap_blast_grenade, snap_hook,
sterilized_bandage, surge_coil, surge_shield_recharger,
tactical_mk1, tactical_mk2, tactical_mk3, tagging_grenade,
trailblazer, trigger_nade, vita_shot, vita_spray, wolfpack,
yank_grenade, yellow_light_stick, zipline
"""

item_ids = [
    item.strip() for item in item_ids.replace("\n", "").split(",") if item.strip()
]


def fallback_name(item_id):
    """Generate a readable name when the API lookup fails."""
    name = item_id.replace("_", " ").title()

    # Format Mk levels consistently
    name = re.sub(r"\bMk(\s+\d+)\b", r"Mk.\1", name)

    # Common game-specific names
    replacements = {
        "Lil Smoke Grenade": "Lil' Smoke Grenade",
        "Dockmasters Detector": "Dockmaster's Detector",
        "Vita Shot": "Vita Shot",
        "Wolfpack": "Wolfpack",
        "Zipline": "Zipline",
    }

    return replacements.get(name, name)


item_names = {}
session = requests.Session()

for item_id in item_ids:
    url = f"https://ardb.app/api/items/{item_id}"

    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()

        item = response.json()
        name = item.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing item name in API response")

        item_names[item_id] = name.strip()

    except (requests.RequestException, ValueError, KeyError) as error:
        item_names[item_id] = fallback_name(item_id)
        print(f"Fallback for {item_id}: {error}")

# Guarantee that no input IDs are missing
assert len(item_names) == len(item_ids)
assert all(item_id in item_names for item_id in item_ids)

# Save complete dictionary
with open("item_names.json", "w", encoding="utf-8") as file:
    json.dump(item_names, file, indent=4, ensure_ascii=False)

print(f"\nSaved {len(item_names)}/{len(item_ids)} items to item_names.json")
print(json.dumps(item_names, indent=4, ensure_ascii=False))
