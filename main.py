import copy
import logging
import os
import re
import threading
import time
from queue import Queue

import pyautogui

import utils
import main_config

import player_main_scanner
import recognition
import ocr_weapons

TEMPLATE_DIR = "item_templates"
BIG_TEMPLATE_DIR = "item_templates_big"
TEMPLATE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

TABS_X = 132
TABS_Y = {
    "augment": 460,
    "shields": 530,
    "weapons": 595,
    "ammo": 660,
    "quickuse": 795,
}

STASH_TABS = recognition.STASH_TABS

AFTER_MOVE_DELAY = 0.05
POPUP_DISMISS_DELAY = 0.05
TAB_SWITCH_DELAY = 0.3
MAX_SCROLL_ATTEMPTS = 50
SCROLLBAR_CLICK_OFFSET = 10
MAX_CLEAR_CLICKS = 50
MAX_UNCHANGED_CLEAR_SCANS = 2
BIG_ITEM_CLICK_DELAY = 0.1
PLAYER_INVENTORY_SAVE_DRAG_DURATION = 0.16
PLAYER_INVENTORY_SAVE_SOURCE_BOTTOM_INSET = 130

PLAYER_INVENTORY_SAVE_SOURCES = (
    (1175, 788),
    (1175, 1076),
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

task_lock = threading.Lock()
task_running = False

status_queue = Queue()
player_inventory_results = Queue()
loadout_results = Queue()
scan_cancel_event = threading.Event()


class ScanCancelled(Exception):
    """Raised when the active inventory or stash operation is cancelled."""


def set_status(message):
    message = str(message)
    if message in ("Ready", "Done", "Saving Loadout\nHold On"):
        status_queue.put(message)


def is_cancelled():
    return scan_cancel_event.is_set()


def raise_if_cancelled():
    if is_cancelled():
        raise ScanCancelled("Operation cancelled.")


def scan_player_inventory():
    global task_running

    with task_lock:
        if task_running:
            return

        task_running = True
        scan_cancel_event.clear()

    def worker():
        global task_running

        try:
            set_status("Saving Loadout\nHold On")

            if not recognition.TEMPLATES or is_cancelled():
                set_status("Ready")
                return

            image = utils.capture_screen()

            if is_cancelled():
                set_status("Ready")
                return

            main_items = recognition.recognize_current_grid(
                image,
                grid_name="player_main",
                check_occupancy=True,
            )

            if is_cancelled():
                set_status("Ready")
                return

            quickuse_items = recognition.recognize_current_grid(
                image,
                grid_name="player_quickuse",
                check_occupancy=True,
            )

            if is_cancelled():
                set_status("Ready")
                return

            augmented_items = recognition.recognize_current_grid(
                image,
                grid_name="player_augmented",
                check_occupancy=True,
            )

            if is_cancelled():
                set_status("Ready")
                return

            big_items = recognition.recognize_big_inventory(image)

            if is_cancelled():
                set_status("Ready")
                return

            player_inventory_results.put(
                {
                    "main_items": main_items + augmented_items + big_items,
                    "quickuse_items": quickuse_items,
                    "image": image,
                }
            )
            set_status("Done")

        except Exception:
            logger.exception("Player inventory scan failed")
            set_status("Ready")

        finally:
            with task_lock:
                task_running = False

    threading.Thread(target=worker, daemon=True).start()


def drag_inventory_item(start, destination):
    pyautogui.moveTo(*start, duration=0.1)
    pyautogui.mouseDown()

    try:
        pyautogui.moveTo(
            *destination,
            duration=PLAYER_INVENTORY_SAVE_DRAG_DURATION,
            tween=pyautogui.linear,
        )
    finally:
        pyautogui.mouseUp()


def refresh_weapon_templates():
    weapons_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        TEMPLATE_DIR,
        "weapons",
    )
    recognition.refresh_weapon_templates(
        weapons_dir,
        TEMPLATE_EXTENSIONS,
        set_status,
    )


def safe_weapon_item_name(name, slot_label):
    item_name = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        name,
    ).strip(" .")
    if not item_name:
        raise RuntimeError(f"OCR returned an invalid item name for {slot_label}.")
    if item_name.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }:
        item_name = f"_{item_name}"
    return item_name


def unique_weapon_item_id(name, slot_label, used_item_ids):
    base_name = safe_weapon_item_name(name, slot_label)
    suffix = 1

    while True:
        item_id = f"{base_name}_{suffix:02d}"
        normalized_id = item_id.casefold()
        if normalized_id not in used_item_ids:
            used_item_ids.add(normalized_id)
            return item_id
        suffix += 1


def perform_player_inventory_save_actions(initial_image=None):
    completed_drags = []
    weapon_item_ids = []
    generated_crop_paths = []

    try:
        raise_if_cancelled()
        logger.info("Player inventory save: analyzing inventory")
        image = initial_image if initial_image is not None else utils.capture_screen()
        grid_result = player_main_scanner.scan_inventory(image)
        raise_if_cancelled()

        occupied_sources = [
            (x, y)
            for x, y in PLAYER_INVENTORY_SAVE_SOURCES
            if utils.has_item_banner_at_bottom_border(image, x, y)
        ]

        empty_boxes = [
            cell for cell in grid_result["cells"] if cell["status"] == "empty_box"
        ]
        empty_boxes.sort(
            key=lambda cell: (cell["column_index"], cell["row_index"])
        )
        logger.info(
            "Player inventory save: found %d occupied source(s) and %d empty slot(s)",
            len(occupied_sources),
            len(empty_boxes),
        )

        if len(empty_boxes) < len(occupied_sources):
            raise RuntimeError(
                f"Expected at least {len(occupied_sources)} "
                f"empty boxes, but found {len(empty_boxes)}."
            )

        if not occupied_sources:
            logger.info("Player inventory save: no occupied source slots; nothing to save")
            return weapon_item_ids

        drag_sources = [
            (x, y - PLAYER_INVENTORY_SAVE_SOURCE_BOTTOM_INSET)
            for x, y in occupied_sources
        ]
        destinations = [
            (cell["x"] + 64, cell["y"] + 64)
            for cell in empty_boxes[: len(occupied_sources)]
        ]
        weapons_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "item_templates",
            "weapons",
        )
        os.makedirs(weapons_dir, exist_ok=True)
        used_item_ids = {
            os.path.splitext(filename)[0].casefold()
            for filename in os.listdir(weapons_dir)
            if filename.lower().endswith(TEMPLATE_EXTENSIONS)
        }

        for source_index, (source, destination) in enumerate(
            zip(drag_sources, destinations),
            start=1,
        ):
            raise_if_cancelled()
            logger.info(
                "[box%d] Starting hover and OCR at %s",
                source_index,
                source,
            )
            weapon_name = ocr_weapons.recognize_weapon_at(
                *source,
                slot_label=f"box{source_index}",
                ocr_reader=recognition.OCR_READER,
            )
            raise_if_cancelled()

            if not weapon_name:
                raise RuntimeError(
                    f"Could not read the item name in source box {source_index}."
                )

            item_id = unique_weapon_item_id(
                weapon_name,
                f"source box {source_index}",
                used_item_ids,
            )
            weapon_item_ids.append(item_id)

            logger.info(
                "[box%d] Dragging item from %s to empty slot %s",
                source_index,
                source,
                destination,
            )
            drag_inventory_item(source, destination)
            completed_drags.append((source, destination))
            raise_if_cancelled()

        raise_if_cancelled()
        logger.info("Player inventory save: capturing moved items for weapon assets")
        pyautogui.moveTo(1355, 650, duration=0.1)

        screenshot = utils.capture_screen()

        for (x, y), item_id in zip(destinations, weapon_item_ids):
            raise_if_cancelled()
            crop = screenshot.crop(
                (
                    x - 64,
                    y - 64,
                    x + 64,
                    y + 64,
                )
            )

            crop_path = os.path.join(weapons_dir, f"{item_id}.png")
            crop.save(crop_path)
            generated_crop_paths.append(crop_path)
            logger.info("Saved weapon crop: %s", crop_path)

        raise_if_cancelled()
        refresh_weapon_templates()
        logger.info(
            "Player inventory save: saved %d weapon asset(s)",
            len(weapon_item_ids),
        )

    except ScanCancelled:
        for crop_path in generated_crop_paths:
            try:
                os.remove(crop_path)
            except OSError:
                logger.exception(
                    "Could not remove weapon crop after cancellation: %s",
                    crop_path,
                )
        raise
    finally:
        for source, destination in reversed(completed_drags):
            logger.info(
                "Player inventory save: restoring item from %s to %s",
                destination,
                source,
            )
            drag_inventory_item(destination, source)
        if completed_drags:
            logger.info("Player inventory save: inventory items restored")

    return weapon_item_ids


def clear_player_inventory():
    global task_running

    with task_lock:
        if task_running:
            return

        task_running = True
        scan_cancel_event.clear()

    def worker():
        global task_running

        try:
            image = utils.capture_screen()

            if is_cancelled():
                set_status("Ready")
                return

            # 1. Main inventory: occupancy detection only.
            main_items = recognition.find_occupied_grid_slots(
                image,
                grid_name="player_main",
            )

            if is_cancelled():
                set_status("Ready")
                return

            # 2. Big inventory boxes retain template recognition.
            if recognition.TEMPLATES and recognition.structural_similarity is not None:
                big_items = recognition.recognize_big_inventory(image)
            else:
                big_items = []
                logger.warning(
                    "Skipping big inventory boxes: recognition "
                    "templates or structural_similarity unavailable."
                )

            if is_cancelled():
                set_status("Ready")
                return

            # 3. Quickslots: occupancy detection only.
            quickuse_items = recognition.find_occupied_grid_slots(
                image,
                grid_name="player_quickuse",
            )

            if is_cancelled():
                set_status("Ready")
                return

            # player_augmented is intentionally not unloaded.
            items = main_items + big_items + quickuse_items

            grid_order = {
                "player_main": 0,
                "player_quickuse": 1,
                "big_inventory": 2,
            }

            items.sort(
                key=lambda item: (
                    grid_order.get(item.get("grid_name"), 3),
                    (
                        0
                        if item.get("box_name") == "box2"
                        else 1 if item.get("box_name") == "box1" else 0
                    ),
                    item.get("y", 0),
                    item.get("x", 0),
                )
            )

            clicks = 0

            for item in items:
                if is_cancelled():
                    break

                if clicks >= MAX_CLEAR_CLICKS:
                    logger.warning(
                        "Inventory clearing reached its safety limit " "of %s clicks.",
                        MAX_CLEAR_CLICKS,
                    )
                    break

                x = item.get("x")
                y = item.get("y")

                if x is None or y is None:
                    logger.warning(
                        "Skipping slot without coordinates: %s",
                        item.get("name", "unknown"),
                    )
                    continue

                pyautogui.doubleClick(
                    x,
                    y,
                    interval=0.06,
                )
                clicks += 1

                if item.get("grid_name") == "big_inventory":
                    time.sleep(BIG_ITEM_CLICK_DELAY)
                else:
                    time.sleep(AFTER_MOVE_DELAY)

            if not is_cancelled():
                weapon_slots_image = utils.capture_screen()
                occupied_weapon_slots = [
                    (x, y - PLAYER_INVENTORY_SAVE_SOURCE_BOTTOM_INSET)
                    for x, y in PLAYER_INVENTORY_SAVE_SOURCES
                    if utils.has_item_banner_at_bottom_border(weapon_slots_image, x, y)
                ]

                logger.info(
                    "Inventory clearing: found %d occupied draggable weapon slot(s)",
                    len(occupied_weapon_slots),
                )
                for x, y in occupied_weapon_slots:
                    if is_cancelled():
                        break

                    pyautogui.doubleClick(x, y, interval=0.06)
                    time.sleep(BIG_ITEM_CLICK_DELAY)

            set_status("Done" if not is_cancelled() else "Ready")

        except Exception:
            logger.exception("Player inventory clearing failed")
            set_status("Ready")

        finally:
            with task_lock:
                task_running = False

    threading.Thread(target=worker, daemon=True).start()


def click_down_from_saved_bounds(saved_bounds):
    if saved_bounds is None or is_cancelled():
        return None, None

    _, scrollbar_bottom = saved_bounds
    click_y = min(
        scrollbar_bottom + SCROLLBAR_CLICK_OFFSET,
        pyautogui.size().height - 1,
    )

    pyautogui.moveTo(
        utils.SCROLLBAR_X,
        click_y,
        duration=0.1,
    )
    time.sleep(POPUP_DISMISS_DELAY)

    if is_cancelled():
        return None, None

    pyautogui.click(utils.SCROLLBAR_X, click_y)
    time.sleep(main_config.SCROLL_SETTLE_DELAY)

    if is_cancelled():
        return None, None

    image = utils.wait_for_settled_screen()
    bounds = utils.detect_scrollbar(image)
    return image, bounds


def alt_shift_click(x, y):
    pyautogui.moveTo(x, y, duration=0.1)

    try:
        pyautogui.keyDown("alt")
        pyautogui.doubleClick(x, y, interval=0.05)
    finally:
        pyautogui.keyUp("alt")


def move_requested_items(
    requested_items,
    remaining=None,
    searchable_names=None,
):
    if not recognition.TEMPLATES or is_cancelled():
        logger.warning(
            "Cannot move requested items: templates unavailable " "or scan cancelled"
        )
        return 0

    if remaining is None:
        remaining = {
            name: max(0, int(count))
            for name, count in requested_items.items()
            if int(count) > 0 and name.casefold() != "empty"
        }

    if searchable_names is None:
        searchable_names = set(remaining)

    if not any(
        count > 0 and name in searchable_names for name, count in remaining.items()
    ):
        return 0

    image = utils.capture_screen()
    current_bounds = utils.detect_scrollbar(image)
    found_stacks = 0

    for scroll_attempt in range(MAX_SCROLL_ATTEMPTS):
        if is_cancelled():
            return found_stacks

        requested_names = {
            name for name in searchable_names if remaining.get(name, 0) > 0
        }

        if not requested_names:
            return found_stacks

        saved_bounds = current_bounds
        lowest_box = utils.find_lowest_complete_box(image)
        empty_row_found = lowest_box is not None and not lowest_box["occupied"]

        tab_templates = [
            template
            for template in recognition.TAB_TEMPLATES.get(
                recognition.CURRENT_TAB,
                [],
            )
            if template["name"] in requested_names
        ]

        if not tab_templates:
            logger.warning(
                "No searchable templates loaded for stash tab '%s'.",
                recognition.CURRENT_TAB,
            )
            return found_stacks

        items = recognition.recognize_current_grid(
            image,
            grid_name="stash",
            requested_names=requested_names,
            templates=tab_templates,
        )

        if is_cancelled():
            return found_stacks

        found_stacks += len(items)

        if recognition.CURRENT_TAB in ("augment", "weapons"):
            items.sort(
                key=lambda item: (
                    -item["score"],
                    item.get("row_top", 0),
                    item.get("slot_index", 0),
                )
            )
            if len(items) > 1:
                logger.info(
                    "Stash viewport: processing %d %s matches from highest SSIM %.2f first",
                    len(items),
                    recognition.CURRENT_TAB,
                    items[0]["score"],
                )
            items_to_process = items
        else:
            items_to_process = reversed(items)

        for item in items_to_process:
            if is_cancelled():
                return found_stacks

            name = item["name"]

            if name not in requested_names or remaining.get(name, 0) <= 0:
                continue

            banner_text = item["banner_text"]

            # Weapons in the weapons stash tab are always single items.
            if recognition.CURRENT_TAB == "weapons":
                stack_size = 1
            elif banner_text is None or not str(banner_text).strip():
                stack_size = 1
            else:
                try:
                    stack_size = int(str(banner_text).strip())
                except (TypeError, ValueError):
                    logger.warning(
                        "Skipping '%s': unreadable quantity %r",
                        name,
                        banner_text,
                    )
                    continue

            if stack_size <= 0:
                logger.warning(
                    "Skipping '%s': invalid stack size %s",
                    name,
                    stack_size,
                )
                continue

            x, y = item["x"], item["y"]

            while stack_size > 0 and remaining[name] > 0:
                if is_cancelled():
                    return found_stacks

                if remaining[name] >= stack_size:
                    amount_moved = stack_size
                    pyautogui.moveTo(x, y, duration=0.1)
                    pyautogui.doubleClick(x, y, interval=0.05)
                else:
                    amount_moved = utils.estimate_items_moved(stack_size)

                    if amount_moved <= 0:
                        break

                    alt_shift_click(x, y)

                time.sleep(AFTER_MOVE_DELAY)
                remaining[name] -= amount_moved
                stack_size -= amount_moved

            if not any(
                count > 0 and eligible_name in searchable_names
                for eligible_name, count in remaining.items()
            ):
                return found_stacks

        if is_cancelled():
            return found_stacks

        if not any(
            count > 0 and name in searchable_names for name, count in remaining.items()
        ):
            return found_stacks

        if empty_row_found or saved_bounds is None:
            break

        next_image, next_bounds = click_down_from_saved_bounds(saved_bounds)

        if is_cancelled():
            return found_stacks

        if next_image is None or next_bounds is None:
            break

        if next_bounds == saved_bounds:
            break

        image = next_image
        current_bounds = next_bounds

    return found_stacks


def open_stash_tab(tab_name):
    if tab_name not in TABS_Y or is_cancelled():
        return False

    x, y = TABS_X, TABS_Y[tab_name]
    pyautogui.moveTo(x, y, duration=0.1)

    if is_cancelled():
        return False

    time.sleep(0.1)

    if is_cancelled():
        return False

    pyautogui.click(x, y)
    recognition.set_current_tab(tab_name)
    time.sleep(TAB_SWITCH_DELAY)

    return not is_cancelled()


def move_items_by_tab(loadout, enabled_tabs=None):
    if not isinstance(loadout, dict) or not recognition.TEMPLATES:
        logger.warning("Cannot process loadout: invalid loadout or no templates loaded")
        return {}

    if enabled_tabs is None:
        enabled_tabs = set(STASH_TABS)
    else:
        enabled_tabs = set(enabled_tabs)
        invalid_tabs = enabled_tabs.difference(STASH_TABS)
        if invalid_tabs:
            logger.warning("Ignoring unknown stash tabs: %s", sorted(invalid_tabs))
            enabled_tabs.intersection_update(STASH_TABS)

    remaining = {}

    for name, count in loadout.items():
        name = str(name).strip()

        if not name or name.casefold() == "empty":
            continue

        try:
            if isinstance(count, bool):
                continue
            quantity = int(count)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid quantity for '%s': %r",
                name,
                count,
            )
            continue

        if quantity > 0:
            remaining[name] = quantity

    if not remaining:
        return remaining

    tab_items = get_tab_items()

    eligible_tabs = {
        name: {
            tab_name
            for tab_name in STASH_TABS
            if tab_name in enabled_tabs
            if name in tab_items.get(tab_name, set())
        }
        for name in remaining
    }

    remaining = {
        name: quantity
        for name, quantity in remaining.items()
        if eligible_tabs[name]
        or not any(name in items for items in tab_items.values())
    }

    if not remaining:
        return remaining

    if "weapons" in enabled_tabs:
        weapons_tab_position = (TABS_X, TABS_Y["weapons"])
        pyautogui.moveTo(*weapons_tab_position, duration=0.1)
        pyautogui.click(*weapons_tab_position)
        recognition.set_current_tab("weapons")
        logger.info("Stash scan: clicked Weapons tab; waiting 0.2s before scanning")
        time.sleep(0.2)

    for tab_name in STASH_TABS:
        if tab_name not in enabled_tabs:
            continue

        if is_cancelled():
            return remaining

        if not any(quantity > 0 for quantity in remaining.values()):
            return remaining

        tab_searchable = {
            name
            for name, quantity in remaining.items()
            if quantity > 0 and tab_name in eligible_tabs.get(name, set())
        }

        try:
            if not tab_searchable:
                continue

            if not open_stash_tab(tab_name):
                return remaining

            found_stacks = move_requested_items(
                remaining,
                remaining=remaining,
                searchable_names=tab_searchable,
            )

            logger.info(
                "Tab '%s' scan complete: %d matching stack(s)",
                tab_name,
                found_stacks,
            )

        finally:
            for name in eligible_tabs:
                eligible_tabs[name].discard(tab_name)

    return remaining


def start_scan(loadout, enabled_tabs=None):
    global task_running

    if not isinstance(loadout, dict):
        logger.warning("Cannot start stash scan: loadout must be a dictionary")
        return

    selected_loadout = copy.deepcopy(loadout)

    with task_lock:
        if task_running:
            logger.warning("Cannot start stash scan: another task is already running")
            return

        scan_cancel_event.clear()
        task_running = True

    def worker():
        global task_running

        try:
            remaining = move_items_by_tab(
                selected_loadout,
                enabled_tabs=enabled_tabs,
            )

            if not is_cancelled():
                pyautogui.moveTo(1000, 260, duration=0.1)

                missing = {
                    name: quantity
                    for name, quantity in remaining.items()
                    if quantity > 0
                }

                result = {
                    "success": not missing,
                    "missing": missing,
                }
                loadout_results.put(result)

                if missing:
                    logger.warning(
                        "Loadout finished with missing items: %s",
                        missing,
                    )

            set_status("Done" if not is_cancelled() else "Ready")

        except Exception:
            logger.exception("Stash item scan/move failed")
            set_status("Ready")

        finally:
            with task_lock:
                task_running = False

    threading.Thread(target=worker, daemon=True).start()


def get_tab_items():
    tab_items = {}

    for tab_name in STASH_TABS:
        tab_dir = os.path.join(TEMPLATE_DIR, tab_name)

        if not os.path.isdir(tab_dir):
            tab_items[tab_name] = set()
            continue

        tab_items[tab_name] = {
            os.path.splitext(filename)[0]
            for filename in os.listdir(tab_dir)
            if filename.lower().endswith(TEMPLATE_EXTENSIONS)
            and os.path.splitext(filename)[0].casefold() != "empty"
        }

    return tab_items


def initialize():
    recognition.initialize(
        TEMPLATE_DIR,
        BIG_TEMPLATE_DIR,
        TEMPLATE_EXTENSIONS,
        set_status,
        is_cancelled,
    )
    set_status("Ready")
