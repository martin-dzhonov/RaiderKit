import copy
import logging
import os
import re
import threading
import time
import random
from queue import Queue

import pyautogui

import utils
import main_config

import player_main_scanner
import recognition


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

PLAYER_INVENTORY_SAVE_SOURCES = (
    (1310, 665),
    (1310, 890),
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


def set_status(message):
    message = str(message)
    if message in ("Ready", "Done") or re.fullmatch(r"Scanning \d+/\d+", message):
        status_queue.put(message)


def is_cancelled():
    return scan_cancel_event.is_set()


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

            generated_loadout = utils.build_player_loadout(
                main_items + augmented_items + big_items,
                quickuse_items,
            )

            player_inventory_results.put(copy.deepcopy(generated_loadout))
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


def perform_player_inventory_save_actions(loadout):
    completed_drags = []
    screenshot_path = None
    grid_result = None
    weapon_item_ids = []

    try:
        # Take an initial screenshot to identify empty boxes.
        image = utils.wait_for_settled_screen()
        grid_result = player_main_scanner.scan_inventory(image)

        empty_boxes = [
            cell for cell in grid_result["cells"] if cell["status"] == "empty_box"
        ]

        if len(empty_boxes) < len(PLAYER_INVENTORY_SAVE_SOURCES):
            raise RuntimeError(
                f"Expected at least {len(PLAYER_INVENTORY_SAVE_SOURCES)} "
                f"empty boxes, but found {len(empty_boxes)}."
            )

        # Select the first two empty boxes in grid order.
        # Coordinates are the centers of the 128x128 boxes.
        destinations = [
            (cell["x"] + 64, cell["y"] + 64)
            for cell in empty_boxes[: len(PLAYER_INVENTORY_SAVE_SOURCES)]
        ]

        # Drag each item into its selected empty box.
        for source, destination in zip(
            PLAYER_INVENTORY_SAVE_SOURCES,
            destinations,
        ):
            drag_inventory_item(source, destination)
            completed_drags.append((source, destination))

        # Move the mouse away before taking the screenshot.
        pyautogui.moveTo(1355, 650, duration=0.1)

        screenshot = utils.wait_for_settled_screen()

        # Scan the screenshot taken after both items have been moved.
        grid_result = player_main_scanner.scan_inventory(screenshot)

        # Save cropped images into item_templates/weapons.
        weapons_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "item_templates",
            "weapons",
        )
        os.makedirs(weapons_dir, exist_ok=True)

        for x, y in destinations:
            crop = screenshot.crop(
                (
                    x - 64,
                    y - 64,
                    x + 64,
                    y + 64,
                )
            )

            # Generate a unique gun ID between 1 and 100000.
            for _ in range(1000):
                item_id = f"gun_{random.randint(1, 100000)}"
                crop_path = os.path.join(
                    weapons_dir,
                    f"{item_id}.png",
                )

                if not os.path.exists(crop_path):
                    crop.save(crop_path)
                    logger.info("Saved weapon crop: %s", crop_path)
                    weapon_item_ids.append(item_id)
                    break
            else:
                raise RuntimeError("Could not generate a unique gun filename.")

        refresh_weapon_templates()

    finally:
        # Restore items in reverse order, even if scanning or saving fails.
        for source, destination in reversed(completed_drags):
            drag_inventory_item(destination, source)

    loadout.update(dict.fromkeys(weapon_item_ids, 1))

    return screenshot_path, grid_result


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

            if not items:
                set_status("Done")
                return

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

        for item in reversed(items):
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


def move_items_by_tab(loadout):
    if not isinstance(loadout, dict) or not recognition.TEMPLATES:
        logger.warning("Cannot process loadout: invalid loadout or no templates loaded")
        return {}

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
            if name in tab_items.get(tab_name, set())
        }
        for name in remaining
    }

    for tab_name in STASH_TABS:
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


def start_scan(loadout):
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
            remaining = move_items_by_tab(selected_loadout)

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
