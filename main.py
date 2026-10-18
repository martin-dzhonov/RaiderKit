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
from common import (
    TEMPLATE_DIR,
    TEMPLATE_EXTENSIONS,
    get_item_categories,
    refresh_item_categories,
)

BIG_TEMPLATE_DIR = "assets/item_templates_big"

TABS_X = 132
TABS_Y = {
    "augment": 460,
    "shields": 530,
    "weapons": 595,
    "ammo": 660,
    "quickuse": 795,
}

AFTER_MOVE_DELAY = 0.04
POPUP_DISMISS_DELAY = 0.04
TAB_SWITCH_DELAY = 0.23
MAX_SCROLL_ATTEMPTS = 50
SCROLLBAR_CLICK_OFFSET = 10
MAX_CLEAR_CLICKS = 50
MAX_UNCHANGED_CLEAR_SCANS = 2
BIG_ITEM_CLICK_DELAY = 0.04
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
    status_queue.put(message)


def is_cancelled():
    return scan_cancel_event.is_set()


def raise_if_cancelled():
    if is_cancelled():
        raise ScanCancelled("Operation cancelled.")


def _start_task_worker(worker, operation):
    """Start a task thread and restore shared state if startup fails."""
    global task_running

    try:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    except Exception:
        with task_lock:
            task_running = False
        logger.exception("Could not start %s worker", operation)
        raise


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
            set_status("Saving Loadout\nHold Still")

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
            set_status("Player inventory scan failed. Check the application log.")

        finally:
            with task_lock:
                task_running = False

    _start_task_worker(worker, "player inventory scan")


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
        empty_boxes.sort(key=lambda cell: (cell["column_index"], cell["row_index"]))

        if len(empty_boxes) < len(occupied_sources):
            raise RuntimeError(
                f"Expected at least {len(occupied_sources)} "
                f"empty boxes, but found {len(empty_boxes)}."
            )

        if not occupied_sources:
            logger.info(
                "Player inventory save: no occupied source slots; nothing to save"
            )
            return weapon_item_ids

        drag_sources = [
            (x, y - PLAYER_INVENTORY_SAVE_SOURCE_BOTTOM_INSET)
            for x, y in occupied_sources
        ]
        destinations = [
            (cell["x"] + 64, cell["y"] + 64)
            for cell in empty_boxes[: len(occupied_sources)]
        ]
        weapons_dir = str(TEMPLATE_DIR / "weapons")
        os.makedirs(weapons_dir, exist_ok=True)
        used_item_ids = {
            item_name.casefold()
            for item_name in get_item_categories().get("weapons", set())
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
            generated_crop_paths.append(crop_path)
            crop.save(crop_path)
            logger.info("Saved weapon crop: %s", crop_path)

        raise_if_cancelled()
        refresh_item_categories()
        refresh_weapon_templates()
        logger.info(
            "Player inventory save: saved %d weapon asset(s)",
            len(weapon_item_ids),
        )

    except ScanCancelled:
        _remove_generated_weapon_crops(generated_crop_paths)
        raise
    except Exception:
        _remove_generated_weapon_crops(generated_crop_paths)
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


def _remove_generated_weapon_crops(crop_paths):
    removed_any = False
    for crop_path in crop_paths:
        try:
            os.remove(crop_path)
            removed_any = True
        except FileNotFoundError:
            continue
        except OSError:
            logger.exception(
                "Could not remove weapon crop after failed save: %s",
                crop_path,
            )

    if removed_any:
        try:
            refresh_item_categories()
        except Exception:
            logger.exception("Could not refresh item category index after cleanup")


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
            set_status("Player inventory clearing failed. Check the application log.")

        finally:
            with task_lock:
                task_running = False

    _start_task_worker(worker, "player inventory clearing")


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


def _item_stack_size(item):
    if recognition.CURRENT_TAB in recognition.SINGLE_ITEM_TABS:
        return 1

    banner_text = item.get("banner_text")
    if banner_text is None or not str(banner_text).strip():
        return 1

    try:
        return int(str(banner_text).strip())
    except (TypeError, ValueError):
        return 0


def _plan_group_moves(sizes, needed):
    """Plan clicks for stacks of one item, given front-to-back stack sizes.

    The game re-sorts same-item stacks by size (descending) after every move,
    so the plan is found by simulating that. Only the backmost stack may be
    emptied. Returns (slot_index, "split" | "all", items_moved) steps that
    move exactly `needed` items if possible, else the smallest overshoot,
    else as many as possible; fewest clicks win ties.
    """

    def rank(path):
        # Fewest clicks first, then prefer acting on backmost stacks.
        return (len(path), tuple(-step[0] for step in path))

    start = tuple(sizes)
    paths = {start: []}
    queue = [start]
    for state in queue:
        for index, size in enumerate(state):
            is_last = index == len(state) - 1
            moves = [("split", utils.estimate_items_moved(size))]
            if is_last:
                moves.append(("all", size))
            for kind, moved in moves:
                if moved == size and not is_last:
                    continue
                rest = list(state)
                if moved == size:
                    rest.pop(index)
                else:
                    rest[index] = size - moved
                new_state = tuple(sorted(rest, reverse=True))
                path = paths[state] + [(index, kind, moved)]
                if new_state not in paths:
                    paths[new_state] = path
                    queue.append(new_state)
                elif len(path) == len(paths[new_state]) and rank(path) < rank(
                    paths[new_state]
                ):
                    paths[new_state] = path

    base = sum(start)
    totals = {}
    for state, path in paths.items():
        total = base - sum(state)
        if total not in totals or rank(path) < rank(totals[total]):
            totals[total] = path

    over = [total for total in totals if total >= needed]
    return totals[min(over) if over else max(totals)]


def _select_best_matches(items, remaining):
    """Pick the highest-SSIM matches per item until the requested amount is covered."""
    by_name = {}
    for item in items:
        by_name.setdefault(item["name"], []).append(item)

    selected = []
    for name, candidates in by_name.items():
        needed = remaining.get(name, 0)
        candidates.sort(key=lambda item: -item["score"])

        for item in candidates:
            if needed <= 0:
                break

            stack_size = _item_stack_size(item)
            if stack_size <= 0:
                continue

            selected.append(item)
            needed -= stack_size

        if len(selected) < len(items):
            logger.info(
                "Stash viewport: selected best %s matches for '%s' (top SSIM %.2f)",
                recognition.CURRENT_TAB,
                name,
                candidates[0]["score"],
            )

    return selected


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

        if recognition.CURRENT_TAB in recognition.SINGLE_ITEM_TABS:
            # Keep only the best-scoring matches needed to fill each request.
            items = _select_best_matches(items, remaining)

        # Always move from the last slot to the first: the grid compacts
        # toward the start, so removing front-first shifts later items.
        items.sort(key=lambda item: (item.get("row_top", 0), item.get("slot_index", 0)))

        # Group stacks of the same item (adjacent because the list is sorted),
        # each group ordered back to front, backmost group first.
        groups = []
        for item in reversed(items):
            if groups and groups[-1][0]["name"] == item["name"]:
                groups[-1].append(item)
            else:
                groups.append([item])

        for group in groups:
            if is_cancelled():
                return found_stacks

            name = group[0]["name"]

            if name not in requested_names or remaining.get(name, 0) <= 0:
                continue

            # Front-to-back slots; stacks of one item are sorted by size.
            slots = []
            sizes = []
            for item in reversed(group):
                stack_size = _item_stack_size(item)
                if stack_size <= 0:
                    logger.warning(
                        "Skipping '%s': unreadable quantity %r",
                        name,
                        item.get("banner_text"),
                    )
                    continue
                slots.append(item)
                sizes.append(stack_size)

            if not slots:
                continue

            for slot_index, kind, amount_moved in _plan_group_moves(
                sizes, remaining[name]
            ):
                if is_cancelled():
                    return found_stacks

                x, y = slots[slot_index]["x"], slots[slot_index]["y"]
                if kind == "all":
                    pyautogui.moveTo(x, y, duration=0.1)
                    pyautogui.doubleClick(x, y, interval=0.05)
                else:
                    alt_shift_click(x, y)

                time.sleep(AFTER_MOVE_DELAY)
                remaining[name] -= amount_moved

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

    pyautogui.click(x, y)
    recognition.set_current_tab(tab_name)
    time.sleep(TAB_SWITCH_DELAY)

    return not is_cancelled()


def move_items_by_tab(loadout, enabled_tabs=None):
    if not isinstance(loadout, dict) or not recognition.TEMPLATES:
        logger.warning("Cannot process loadout: invalid loadout or no templates loaded")
        return {}

    tab_items = get_item_categories()
    stash_tabs = tuple(tab_items)
    if enabled_tabs is None:
        enabled_tabs = set(stash_tabs)
    else:
        enabled_tabs = set(enabled_tabs)
        invalid_tabs = enabled_tabs.difference(stash_tabs)
        if invalid_tabs:
            logger.warning("Ignoring unknown stash tabs: %s", sorted(invalid_tabs))
            enabled_tabs.intersection_update(stash_tabs)

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

    eligible_tabs = {
        name: {
            tab_name
            for tab_name in stash_tabs
            if tab_name in enabled_tabs
            if name in tab_items.get(tab_name, set())
        }
        for name in remaining
    }

    remaining = {
        name: quantity
        for name, quantity in remaining.items()
        if eligible_tabs[name] or not any(name in items for items in tab_items.values())
    }

    if not remaining:
        return remaining

    for tab_name in stash_tabs:
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

            if tab_name == "weapons":
                # Weapons > Shields > Weapons refresh before scanning weapons.
                for refresh_tab in ("shields", "weapons"):
                    if not open_stash_tab(refresh_tab):
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

        except Exception as exc:
            logger.exception("Stash item scan/move failed")
            loadout_results.put(
                {
                    "success": False,
                    "missing": {},
                    "error": str(exc) or type(exc).__name__,
                }
            )
            set_status("Ready")

        finally:
            with task_lock:
                task_running = False

    _start_task_worker(worker, "loadout equip")


def initialize():
    get_item_categories()
    recognition.initialize(
        TEMPLATE_DIR,
        BIG_TEMPLATE_DIR,
        TEMPLATE_EXTENSIONS,
        set_status,
        is_cancelled,
    )
    set_status("Ready")
