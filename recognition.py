import logging
import os
import re
import warnings
from pathlib import Path

import easyocr
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import utils
from common import get_item_categories

warnings.filterwarnings(
    "ignore",
    message="'pin_memory' argument is set as true but no accelerator is found.*",
    category=UserWarning,
)

try:
    from skimage.metrics import structural_similarity
except ImportError:
    structural_similarity = None


MIN_SIMILARITY = 83.0
MIN_WEAPON_TIER_SIMILARITY = 70.0
MIN_WEAPON_ATTACHMENT_SIMILARITY = 61.0
OCR_SCALE_FACTOR = 3
ICON_BORDER_INSET = 5
WEAPON_TIER_REGION_SIZE = 30
WEAPON_TIER_TOP_LEFT_INSET = 0
WEAPON_TIER_BOTTOM_RIGHT_INSET = 2
WEAPON_ATTACHMENT_REGION_SIZE = 30
WEAPON_ATTACHMENT_RIGHT_INSET = 50
BOXES = {
    "box1": (923, 363, 1115, 491),
    "box2": (1136, 363, 1328, 491),
}

logger = logging.getLogger(__name__)
SSIM_DEBUG_DIR = Path(__file__).resolve().parent / "SSIM_debug"

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


def save_ssim_debug_pair(
    candidate_array,
    template_array,
    template_name,
    row,
    column,
    score,
    area=None,
    row_directories=None,
):
    prefix = f"r{row}_c{column}"
    if area:
        prefix = f"{prefix}_{area}"
    prefix = f"{prefix}_{score:.2f}"

    try:
        if row_directories is None:
            row_directories = {}

        safe_template_name = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            str(template_name),
        ).strip(" .")
        if not safe_template_name:
            safe_template_name = "unknown_template"
        if safe_template_name.upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
        }:
            safe_template_name = f"_{safe_template_name}"

        template_dir = SSIM_DEBUG_DIR / safe_template_name
        row_key = (safe_template_name, row)
        row_dir = row_directories.get(row_key)
        if row_dir is None:
            row_name = f"row_{row}"
            suffix = 1
            while True:
                folder_name = row_name if suffix == 1 else f"{row_name}_{suffix}"
                row_dir = template_dir / folder_name
                try:
                    row_dir.mkdir(parents=True, exist_ok=False)
                    break
                except FileExistsError:
                    suffix += 1
            row_directories[row_key] = row_dir

        Image.fromarray(candidate_array).save(row_dir / f"{prefix}_1_grid.png")
        Image.fromarray(template_array).save(row_dir / f"{prefix}_2_template.png")
    except OSError:
        logger.exception(
            "Could not save SSIM debug images for row %d, column %d",
            row,
            column,
        )


def compare_banner_for_diagnostics(
    cell_image,
    grid_config,
    row,
    column,
    matched_template=None,
    row_directories=None,
):
    if structural_similarity is None or matched_template is None:
        return None

    try:
        item_width = grid_config["item_width"]
        item_height = grid_config["item_height"]
        region_size = WEAPON_TIER_REGION_SIZE
        top_left_inset = WEAPON_TIER_TOP_LEFT_INSET
        bottom_right_inset = WEAPON_TIER_BOTTOM_RIGHT_INSET
        if region_size > item_width or region_size > item_height:
            raise ValueError("Weapon tier region exceeds item dimensions")
        if (
            top_left_inset < 0
            or bottom_right_inset < 0
            or top_left_inset + bottom_right_inset >= region_size
        ):
            raise ValueError("Weapon tier insets must leave a non-empty region")

        candidate = cell_image.convert("RGB").resize(
            (item_width, item_height),
            Image.Resampling.LANCZOS,
        )
        candidate_array = np.asarray(candidate, dtype=np.uint8)[
            item_height
            - region_size
            + top_left_inset : item_height
            - bottom_right_inset,
            item_width - region_size + top_left_inset : item_width - bottom_right_inset,
        ]
        template_region = matched_template["image"][
            item_height
            - region_size
            + top_left_inset : item_height
            - bottom_right_inset,
            item_width - region_size + top_left_inset : item_width - bottom_right_inset,
        ]
        score = (
            structural_similarity(
                candidate_array,
                template_region,
                channel_axis=2,
                data_range=255,
            )
            * 100.0
        )
        logger.info(
            "Weapon tier SSIM: row=%d col=%d template=%s score=%.2f",
            row,
            column,
            matched_template["name"],
            score,
        )
        # save_ssim_debug_pair(
        #     candidate_array,
        #     template_region,
        #     matched_template["name"],
        #     row,
        #     column,
        #     score,
        #     area="weapon_tier",
        #     row_directories=row_directories,
        # )
        return score
    except Exception:
        logger.exception(
            "Weapon tier SSIM failed for row %d, column %d",
            row,
            column,
        )
        return None


def compare_weapon_attachments_for_diagnostics(
    cell_image,
    grid_config,
    row,
    column,
    matched_template=None,
    row_directories=None,
):
    if structural_similarity is None or matched_template is None:
        return None

    try:
        item_width = grid_config["item_width"]
        item_height = grid_config["item_height"]
        region_size = WEAPON_ATTACHMENT_REGION_SIZE
        right_inset = WEAPON_ATTACHMENT_RIGHT_INSET
        top_left_inset = WEAPON_TIER_TOP_LEFT_INSET
        bottom_right_inset = WEAPON_TIER_BOTTOM_RIGHT_INSET
        if (
            region_size > item_width
            or region_size > item_height
            or right_inset < 0
            or right_inset + region_size > item_width
        ):
            raise ValueError("Weapon attachment region exceeds item dimensions")

        candidate = cell_image.convert("RGB").resize(
            (item_width, item_height),
            Image.Resampling.LANCZOS,
        )
        x_start = item_width - right_inset - region_size
        x_end = item_width - right_inset
        candidate_array = np.asarray(candidate, dtype=np.uint8)[
            item_height
            - region_size
            + top_left_inset : item_height
            - bottom_right_inset,
            x_start:x_end,
        ]
        template_region = matched_template["image"][
            item_height
            - region_size
            + top_left_inset : item_height
            - bottom_right_inset,
            x_start:x_end,
        ]
        score = (
            structural_similarity(
                candidate_array,
                template_region,
                channel_axis=2,
                data_range=255,
            )
            * 100.0
        )
        logger.info(
            "Weapon attachment SSIM: row=%d col=%d template=%s score=%.2f",
            row,
            column,
            matched_template["name"],
            score,
        )
        # save_ssim_debug_pair(
        #     candidate_array,
        #     template_region,
        #     matched_template["name"],
        #     row,
        #     column,
        #     score,
        #     area="weapon_attachments",
        #     row_directories=row_directories,
        # )
        return score
    except Exception:
        logger.exception(
            "Weapon attachment SSIM failed for row %d, column %d",
            row,
            column,
        )
        return None


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

    for tab_name in get_item_categories():
        tab_dir = os.path.join(template_dir, tab_name)
        loaded_templates = utils.load_templates(
            tab_dir,
            stash_config["item_width"],
            stash_config["item_height"],
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


def find_best_match(
    cell_image,
    grid_config=None,
    templates=None,
    debug_row=1,
    debug_column=1,
    row_directories=None,
):
    if structural_similarity is None:
        return None, 0.0, None, None

    if grid_config is None:
        grid_config = utils.GRID_CONFIGS["stash"]

    if templates is None:
        templates = TEMPLATES

    if not templates:
        return None, 0.0, None, None

    item_width = grid_config["item_width"]
    item_height = grid_config["item_height"]
    icon_height = grid_config["icon_height"]

    try:
        candidate = cell_image.convert("RGB").resize(
            (item_width, item_height),
            Image.Resampling.LANCZOS,
        )
        candidate_array = np.asarray(candidate, dtype=np.uint8)[
            ICON_BORDER_INSET:icon_height,
            ICON_BORDER_INSET : item_width - ICON_BORDER_INSET,
        ]
        best_name = None
        best_score = -1.0
        tier_validation_score = None
        attachment_validation_score = None
        is_weapon_stash = (
            grid_config is utils.GRID_CONFIGS["stash"] and CURRENT_TAB == "weapons"
        )

        for template in templates:
            template_icon = template["image"][
                ICON_BORDER_INSET:icon_height,
                ICON_BORDER_INSET : item_width - ICON_BORDER_INSET,
            ]
            score = (
                structural_similarity(
                    candidate_array,
                    template_icon,
                    channel_axis=2,
                    data_range=255,
                )
                * 100.0
            )

            # save_ssim_debug_pair(
            #     candidate_array,
            #     template_icon,
            #     template["name"],
            #     debug_row,
            #     debug_column,
            #     score,
            #     row_directories=row_directories,
            # )

            template_validation_score = None
            template_attachment_score = None
            if is_weapon_stash:
                template_validation_score = compare_banner_for_diagnostics(
                    cell_image,
                    grid_config,
                    debug_row,
                    debug_column,
                    matched_template=template,
                    row_directories=row_directories,
                )
                template_attachment_score = compare_weapon_attachments_for_diagnostics(
                    cell_image,
                    grid_config,
                    debug_row,
                    debug_column,
                    matched_template=template,
                    row_directories=row_directories,
                )

            if score > best_score:
                best_name = template["name"]
                best_score = score
                tier_validation_score = template_validation_score
                attachment_validation_score = template_attachment_score

        return (
            best_name,
            max(0.0, best_score),
            tier_validation_score,
            attachment_validation_score,
        )

    except Exception:
        logger.exception("Template matching failed")
        return None, 0.0, None, None


def recognize_big_inventory(image):
    observations = []

    if not BIG_TEMPLATES or structural_similarity is None:
        return observations

    row_directories = {}

    for box_index, (box_name, bounds) in enumerate(BOXES.items(), start=1):
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
        best_template = None

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
                    best_template = template

            except Exception:
                continue

        # if best_template is not None:
        #     save_ssim_debug_pair(
        #         candidate_array,
        #         best_template["image"],
        #         best_template["name"],
        #         1,
        #         box_index,
        #         best_score,
        #         row_directories=row_directories,
        #     )

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
    row_number=1,
    grid_config=None,
    requested_names=None,
    templates=None,
    check_occupancy=False,
    row_directories=None,
):
    if grid_config is None:
        grid_config = utils.GRID_CONFIGS["stash"]

    item_width = grid_config["item_width"]
    item_height = grid_config["item_height"]
    icon_height = grid_config["icon_height"]
    x_end = column_x + item_width
    y_end = row_top + item_height

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
    name, score, tier_validation_score, attachment_validation_score = find_best_match(
        cell,
        grid_config=grid_config,
        templates=templates,
        debug_row=row_number,
        debug_column=slot_index,
        row_directories=row_directories,
    )
    if name is None or score < MIN_SIMILARITY:
        return None

    is_weapon_tab = (
        grid_config is utils.GRID_CONFIGS["stash"] and CURRENT_TAB == "weapons"
    )
    if is_weapon_tab and (
        tier_validation_score is None
        or tier_validation_score < MIN_WEAPON_TIER_SIMILARITY
        or attachment_validation_score is None
        or attachment_validation_score < MIN_WEAPON_ATTACHMENT_SIMILARITY
    ):
        logger.info(
            "Rejected weapon recognition: row=%d slot=%d item=%s "
            "icon_score=%.2f tier_score=%s tier_threshold=%.2f "
            "attachment_score=%s attachment_threshold=%.2f",
            row_number,
            slot_index,
            name,
            score,
            (
                f"{tier_validation_score:.2f}"
                if tier_validation_score is not None
                else "unavailable"
            ),
            MIN_WEAPON_TIER_SIMILARITY,
            (
                f"{attachment_validation_score:.2f}"
                if attachment_validation_score is not None
                else "unavailable"
            ),
            MIN_WEAPON_ATTACHMENT_SIMILARITY,
        )
        return None

    if grid_config is utils.GRID_CONFIGS["stash"] and name.casefold() == "empty":
        return None

    if is_weapon_tab:
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
    row_directories = {}

    for row_number, row in enumerate(rows, start=1):
        if _is_cancelled is not None and _is_cancelled():
            break

        for slot_index, column_x in enumerate(columns, start=1):
            if _is_cancelled is not None and _is_cancelled():
                break

            item = recognize_slot(
                image,
                row["top"],
                slot_index,
                column_x,
                row_number=row_number,
                grid_config=grid_config,
                requested_names=requested_names,
                templates=templates,
                check_occupancy=check_occupancy,
                row_directories=row_directories,
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
