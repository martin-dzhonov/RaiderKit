import logging
import time

import easyocr
import numpy as np
import pyautogui

WEAPON_HOVER_DELAY = 0.2

POPUP_BACKGROUND = (249, 238, 223)
POPUP_CONTENT_OFFSET = 33

ICON_COLORS = {
    (232, 134, 41),
    (255, 198, 0),
    (204, 48, 153),
    (0, 169, 242),
    (38, 191, 87),
    (108, 108, 108),
}

logger = logging.getLogger(__name__)
_OCR_READER = None


def get_ocr_reader():
    global _OCR_READER

    if _OCR_READER is None:
        _OCR_READER = easyocr.Reader(["en"], gpu=False)

    return _OCR_READER


def find_popup_left_border(image, start_x, y):
    """Find the popup's left border by detecting its background color."""
    if y < 0 or y >= image.height:
        return None

    pixels = image.convert("RGB").load()

    for x in range(max(0, start_x), image.width - 1):
        if pixels[x, y] == POPUP_BACKGROUND and pixels[x + 1, y] == POPUP_BACKGROUND:
            return x, y

    return None


def find_icon(image, popup_x, mouse_y):
    """Find the popup icon using its known colors."""
    x = popup_x + POPUP_CONTENT_OFFSET

    if x < 0 or x >= image.width:
        return None

    pixels = image.convert("RGB").load()

    for y in range(min(mouse_y, image.height - 1), -1, -1):
        color = pixels[x, y]

        if color in ICON_COLORS:
            return x, y, color

    return None


def recognize_weapon_at(x, y, slot_label="weapon", ocr_reader=None):
    """
    Hover over a weapon slot, detect its popup, OCR the text,
    and return the recognized weapon name.

    Args:
        x: Screen X coordinate of the weapon slot.
        y: Screen Y coordinate of the weapon slot.
        slot_label: Label identifying the weapon slot.

    Returns:
        The recognized weapon name, or None if recognition fails.
    """
    pyautogui.moveTo(x, y, duration=0.1)
    time.sleep(WEAPON_HOVER_DELAY)

    screenshot = pyautogui.screenshot()

    popup_position = find_popup_left_border(
        screenshot,
        start_x=x + 1,
        y=y,
    )

    if popup_position is None:
        logger.warning("[%s] Weapon not recognized: popup not found", slot_label)
        return None

    popup_x, _ = popup_position

    icon_result = find_icon(
        screenshot,
        popup_x,
        mouse_y=y,
    )

    if icon_result is None:
        logger.warning("[%s] Weapon not recognized: icon not found", slot_label)
        return None

    icon_x, icon_y, _ = icon_result

    left = max(0, icon_x - 5)
    top = max(0, icon_y + 5)
    right = min(left + 300, screenshot.width)
    bottom = min(top + 50, screenshot.height)

    if right <= left or bottom <= top:
        logger.warning("[%s] Weapon not recognized: invalid OCR crop", slot_label)
        return None

    ocr_crop = screenshot.crop((left, top, right, bottom))

    if ocr_reader is None:
        ocr_reader = get_ocr_reader()

    results = ocr_reader.readtext(
        np.array(ocr_crop.convert("RGB")),
        detail=0,
        paragraph=False,
        allowlist=(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "abcdefghijklmnopqrstuvwxyz" "0123456789 "
        ),
        decoder="beamsearch",
        text_threshold=0.5,
        low_text=0.3,
        link_threshold=0.3,
        contrast_ths=0.1,
        adjust_contrast=0.7,
        mag_ratio=2,
    )

    weapon_name = " ".join(text.strip() for text in results if text.strip())

    if weapon_name:
        logger.info("[%s] Weapon recognized: %s", slot_label, weapon_name)
        return weapon_name

    logger.warning("[%s] Weapon not recognized: no OCR text", slot_label)
    return None


def recognize_player_guns(ocr_reader=None):
    """
    Compatibility wrapper for the previous hardcoded player-gun scan.

    Update these coordinates if needed.
    Stash scanning should call recognize_weapon_at(x, y) directly.
    """
    weapon_boxes = {
        "box1": (1300, 645),
        "box2": (1300, 940),
    }

    detected_popups = {}

    for box_name, (x, y) in weapon_boxes.items():
        weapon_name = recognize_weapon_at(
            x,
            y,
            slot_label=box_name,
            ocr_reader=ocr_reader,
        )

        detected_popups[box_name] = {
            "weapon_name": weapon_name,
        }

    return detected_popups
