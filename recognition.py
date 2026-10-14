import logging
import os
import re
import warnings

import easyocr
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import utils

warnings.filterwarnings(
    "ignore",
    message="'pin_memory' argument is set as true but no accelerator is found.*",
    category=UserWarning,
)

try:
    from skimage.metrics import structural_similarity
except ImportError:
    structural_similarity = None


MIN_SIMILARITY = 81.0
OCR_SCALE_FACTOR = 3
STASH_TABS = ("augment", "shields", "weapons", "ammo", "quickuse")
BOXES = {
    "box1": (923, 363, 1115, 491),
    "box2": (1136, 363, 1328, 491),
}

logger = logging.getLogger(__name__)

TEMPLATES = []
TAB_TEMPLATES = {}
BIG_TEMPLATES = []
OCR_READER = None
CURRENT_TAB = None

_set_status = None
_is_cancelled = None


def set_runtime_callbacks(set_status, is_cancelled):
    global _set_status, _is_cancelled
    _set_status = set_status
    _is_cancelled = is_cancelled


def set_current_tab(tab_name):
    global CURRENT_TAB
    CURRENT_TAB = tab_name


def initialize(
    template_dir,
    big_template_dir,
    template_extensions,
    set_status,
    is_cancelled,
):
    global TEMPLATES, TAB_TEMPLATES, BIG_TEMPLATES, OCR_READER

    set_runtime_callbacks(set_status, is_cancelled)
    stash_config = utils.GRID_CONFIGS["stash"]
    TAB_TEMPLATES = {}
    TEMPLATES = []

    for tab_name in STASH_TABS:
        tab_dir = os.path.join(template_dir, tab_name)
        loaded_templates = utils.load_templates(
            tab_dir,
            stash_config["item_width"],
            stash_config["item_height"],
            stash_config["icon_height"],
            template_extensions,
            structural_similarity,
            set_status,
        )
        TEMPLATES.extend(loaded_templates)
        TAB_TEMPLATES[tab_name] = [
            template
            for template in loaded_templates
            if str(template.get("name", "")).casefold() != "empty"
        ]

    BIG_TEMPLATES = utils.load_templates(
        big_template_dir,
        192,
        128,
        128,
        template_extensions,
        structural_similarity,
        set_status,
    )

    if structural_similarity is None:
        logger.warning(
            "scikit-image is unavailable; image template recognition is disabled"
        )

    try:
        OCR_READER = easyocr.Reader(
            ["en"],
            gpu=False,
            verbose=False,
        )
    except Exception:
        OCR_READER = None
        logger.exception("Failed to initialize EasyOCR")


def refresh_weapon_templates(weapons_dir, template_extensions, set_status):
    global TEMPLATES

    stash_config = utils.GRID_CONFIGS["stash"]
    previous_template_ids = {
        id(template) for template in TAB_TEMPLATES.get("weapons", [])
    }
    TEMPLATES[:] = [
        template for template in TEMPLATES if id(template) not in previous_template_ids
    ]
    weapon_templates = utils.load_templates(
        weapons_dir,
        stash_config["item_width"],
        stash_config["item_height"],
        stash_config["icon_height"],
        template_extensions,
        structural_similarity,
        set_status,
    )
    weapon_templates = [
        template
        for template in weapon_templates
        if str(template.get("name", "")).casefold() != "empty"
    ]
    TEMPLATES.extend(weapon_templates)
    TAB_TEMPLATES["weapons"] = weapon_templates


def read_banner_text(image, row_top, column_x, grid_config=None):
    if OCR_READER is None:
        return ""

    if grid_config is None:
        grid_config = utils.GRID_CONFIGS["stash"]

    icon_height = grid_config["icon_height"]
    item_width = grid_config["item_width"]
    banner_height = grid_config["banner_height"]
    banner_width = grid_config["banner_width"]

    if grid_config is utils.GRID_CONFIGS["stash"] and CURRENT_TAB == "ammo":
        banner_width = 40

    banner_y = row_top + icon_height
    banner_bottom = banner_y + banner_height
    text_x_end = column_x + item_width - 2
    text_x_start = text_x_end - banner_width

    if (
        banner_y < 0
        or banner_bottom > image.height
        or text_x_start < 0
        or text_x_end > image.width
    ):
        return ""

    try:
        banner = image.crop((text_x_start, banner_y, text_x_end, banner_bottom))
        processed = banner.resize(
            (
                banner.width * OCR_SCALE_FACTOR,
                banner.height * OCR_SCALE_FACTOR,
            ),
            Image.Resampling.LANCZOS,
        )
        processed = ImageOps.grayscale(processed)
        processed = ImageOps.autocontrast(processed)
        processed = ImageEnhance.Contrast(processed).enhance(2.0)
        processed = processed.filter(ImageFilter.SHARPEN)

        results = OCR_READER.readtext(
            np.asarray(processed),
            detail=0,
            paragraph=False,
            allowlist="0123456789xX×",
        )
        text = "".join(str(value).strip() for value in results if str(value).strip())
        text = text.replace("×", "x").lower()
        match = re.search(r"x?(\d+)", text)

        return match.group(1) if match else ""

    except Exception:
        return ""


def find_best_match(cell_image, grid_config=None, templates=None):
    if structural_similarity is None:
        return None, 0.0

    if grid_config is None:
        grid_config = utils.GRID_CONFIGS["stash"]

    if templates is None:
        templates = TEMPLATES

    if not templates:
        return None, 0.0

    item_width = grid_config["item_width"]
    icon_height = grid_config["icon_height"]

    try:
        candidate = cell_image.convert("RGB").resize(
            (item_width, icon_height),
            Image.Resampling.LANCZOS,
        )
        candidate_array = np.asarray(candidate, dtype=np.uint8)

        best_name = None
        best_score = -1.0

        for template in templates:
            score = (
                structural_similarity(
                    candidate_array,
                    template["image"],
                    channel_axis=2,
                    data_range=255,
                )
                * 100.0
            )

            if score > best_score:
                best_name = template["name"]
                best_score = score

        return best_name, max(0.0, best_score)

    except Exception:
        logger.exception("Template matching failed")
        return None, 0.0


def recognize_big_inventory(image):
    observations = []

    if not BIG_TEMPLATES or structural_similarity is None:
        return observations

    for box_name, bounds in BOXES.items():
        if _is_cancelled is not None and _is_cancelled():
            break

        x1, y1, x2, y2 = bounds

        if (
            x1 < 0
            or y1 < 0
            or x2 > image.width
            or y2 > image.height
            or x2 <= x1
            or y2 <= y1
        ):
            logger.warning(
                "Skipping big inventory box '%s': invalid bounds %s",
                box_name,
                bounds,
            )
            continue

        cell = image.crop(bounds).convert("RGB")
        candidate_array = np.asarray(cell, dtype=np.uint8)
        best_name = None
        best_score = -1.0

        for template in BIG_TEMPLATES:
            try:
                score = (
                    structural_similarity(
                        candidate_array,
                        template["image"],
                        channel_axis=2,
                        data_range=255,
                    )
                    * 100.0
                )

                if score > best_score:
                    best_name = template["name"]
                    best_score = score

            except Exception:
                continue

        if best_name is None or best_score < MIN_SIMILARITY:
            continue

        if best_name.casefold() == "empty":
            continue

        logger.info(
            "SSIM recognized big inventory item: box=%s item=%s "
            "score=%.2f threshold=%.2f",
            box_name,
            best_name,
            best_score,
            MIN_SIMILARITY,
        )

        observations.append(
            {
                "name": best_name,
                "score": best_score,
                "banner_text": "1",
                "box_name": box_name,
                "grid_name": "big_inventory",
                "x": (x1 + x2) // 2,
                "y": (y1 + y2) // 2,
            }
        )

    return observations


def find_occupied_grid_slots(image, grid_name):
    """Find occupied player slots using banner pixels only."""
    if grid_name not in (
        "player_main",
        "player_quickuse",
        "player_augmented",
    ):
        raise ValueError(f"Unsupported occupancy-only grid: {grid_name}")

    grid_config = utils.GRID_CONFIGS[grid_name]
    rows = utils.detect_grid_rows(
        image,
        config=grid_config,
        allow_empty_banner=True,
    )

    columns = grid_config["column_x"]
    item_width = grid_config["item_width"]
    icon_height = grid_config["icon_height"]
    items = []

    for row in rows:
        if _is_cancelled is not None and _is_cancelled():
            break

        for slot_index, column_x in enumerate(columns, start=1):
            if _is_cancelled is not None and _is_cancelled():
                break

            occupied = utils.has_item_banner(
                image,
                row["top"],
                column_x,
                config=grid_config,
            )

            if not occupied:
                continue

            items.append(
                {
                    "name": "occupied",
                    "score": 100.0,
                    "banner_text": "",
                    "x": column_x + item_width // 2,
                    "y": row["top"] + icon_height // 2,
                    "row_top": row["top"],
                    "slot_index": slot_index,
                    "grid_name": grid_name,
                }
            )

    logger.info(
        "Occupancy scan for '%s': found %d occupied slot(s)",
        grid_name,
        len(items),
    )

    return items


def recognize_slot(
    image,
    row_top,
    slot_index,
    column_x,
    grid_config=None,
    requested_names=None,
    templates=None,
    check_occupancy=False,
):
    if grid_config is None:
        grid_config = utils.GRID_CONFIGS["stash"]

    item_width = grid_config["item_width"]
    icon_height = grid_config["icon_height"]
    x_end = column_x + item_width
    y_end = row_top + icon_height

    if column_x < 0 or x_end > image.width or row_top < 0 or y_end > image.height:
        return None

    if check_occupancy and not utils.has_item_banner(
        image,
        row_top,
        column_x,
        config=grid_config,
    ):
        return None

    cell = image.crop((column_x, row_top, x_end, y_end))
    name, score = find_best_match(
        cell,
        grid_config=grid_config,
        templates=templates,
    )

    if name is None or score < MIN_SIMILARITY:
        return None

    if grid_config is utils.GRID_CONFIGS["stash"] and name.casefold() == "empty":
        return None

    if grid_config is utils.GRID_CONFIGS["stash"] and CURRENT_TAB == "weapons":
        banner_text = "1"
    else:
        should_read_quantity = requested_names is None or name in requested_names
        banner_text = ""

        if should_read_quantity:
            banner_text = read_banner_text(
                image,
                row_top,
                column_x,
                grid_config=grid_config,
            )

    return {
        "name": name,
        "score": score,
        "banner_text": banner_text,
        "x": column_x + item_width // 2,
        "y": row_top + icon_height // 2,
        "row_top": row_top,
        "slot_index": slot_index,
    }


def recognize_current_grid(
    image,
    grid_name="stash",
    requested_names=None,
    templates=None,
    check_occupancy=False,
):
    observations = []

    if templates is None:
        templates = TEMPLATES

    if not templates:
        logger.warning(
            "Grid '%s' scan skipped: no templates loaded",
            grid_name,
        )
        return observations

    if grid_name not in utils.GRID_CONFIGS:
        raise ValueError(f"Unknown grid configuration: {grid_name}")

    grid_config = utils.GRID_CONFIGS[grid_name]

    if grid_name == "stash" and CURRENT_TAB == "ammo":
        grid_config = {**grid_config, "scan_x": 275}

    rows = utils.detect_grid_rows(
        image,
        config=grid_config,
        allow_empty_banner=(grid_name != "stash"),
    )

    columns = grid_config["column_x"]
    total = len(rows) * len(columns)
    current = 0

    for row_number, row in enumerate(rows, start=1):
        if _is_cancelled is not None and _is_cancelled():
            break

        for slot_index, column_x in enumerate(columns, start=1):
            if _is_cancelled is not None and _is_cancelled():
                break

            current += 1
            if total > 0:
                if _set_status is not None:
                    _set_status(f"Scanning {current}/{total}")

            item = recognize_slot(
                image,
                row["top"],
                slot_index,
                column_x,
                grid_config=grid_config,
                requested_names=requested_names,
                templates=templates,
                check_occupancy=check_occupancy,
            )

            if item is not None:
                item["grid_name"] = grid_name
                observations.append(item)
                logger.info(
                    "SSIM recognized inventory item: grid=%s row=%d slot=%d "
                    "item=%s score=%.2f threshold=%.2f",
                    grid_name,
                    row_number,
                    slot_index,
                    item["name"],
                    item["score"],
                    MIN_SIMILARITY,
                )

    return observations


def recognize_player_inventory(image):
    items = []
    items.extend(
        recognize_current_grid(
            image,
            grid_name="player_main",
            check_occupancy=True,
        )
    )

    if _is_cancelled is not None and _is_cancelled():
        return items

    items.extend(
        recognize_current_grid(
            image,
            grid_name="player_quickuse",
            check_occupancy=True,
        )
    )

    if _is_cancelled is not None and _is_cancelled():
        return items

    items.extend(
        recognize_current_grid(
            image,
            grid_name="player_augmented",
            check_occupancy=True,
        )
    )

    if _is_cancelled is not None and _is_cancelled():
        return items

    items.extend(recognize_big_inventory(image))
    return items
