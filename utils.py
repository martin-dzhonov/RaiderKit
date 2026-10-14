import os
import time

import mss
import numpy as np
from PIL import Image

from main_config import (
    GRID_CONFIGS,
    SCAN_X,
    SCAN_START_Y,
    BOTTOM_SCAN_Y,
    ITEM_HEIGHT,
    BORDER_WIDTH,
    MIN_BORDER_DISTANCE,
    BORDER_HEIGHT_TOLERANCE,
    BANNER_COLOR,
    BANNER_HEIGHT,
    ROW_BORDER_MAX_RUN,
    ROW_BANNER_MIN_RUN,
    SCROLLBAR_X,
    SCROLLBAR_START_Y,
    SCROLLBAR_END_Y,
    SCROLLBAR_COLORS,
)


def capture_screen():
    with mss.mss() as screenshotter:
        captured = screenshotter.grab(screenshotter.monitors[1])
        return Image.frombytes("RGB", captured.size, captured.rgb)


def wait_for_settled_screen(previous_image=None):
    time.sleep(0.30)
    return capture_screen()


def color_distance(a, b):
    return sum((int(a[i]) - int(b[i])) ** 2 for i in range(3)) ** 0.5


def is_border(image, x, y):
    if x < 0 or x >= image.width or y < 1 or y + 1 >= image.height:
        return False

    pixels = image.load()
    current = pixels[x, y][:3]
    above = pixels[x, y - 1][:3]
    below = pixels[x, y + 1][:3]

    return (
        color_distance(current, above) >= MIN_BORDER_DISTANCE
        and color_distance(current, below) >= MIN_BORDER_DISTANCE
    )


def find_border_candidates(image, x, y_start, y_end):
    y_start = max(1, y_start)
    y_end = min(y_end, image.height - 2)

    raw = []

    for y in range(y_start, y_end):
        if is_border(image, x, y) and is_border(image, x, y + 1):
            raw.append(y)

    if not raw:
        return []

    groups = [[raw[0]]]

    for y in raw[1:]:
        if y <= groups[-1][-1] + 2:
            groups[-1].append(y)
        else:
            groups.append([y])

    return [round(sum(group) / len(group)) for group in groups]


def detect_complete_boxes(image):
    grid_bottom = min(BOTTOM_SCAN_Y, image.height - 1)

    borders = find_border_candidates(
        image,
        SCAN_X,
        SCAN_START_Y,
        grid_bottom,
    )

    boxes = []

    for i, top in enumerate(borders):
        expected_bottom = top + ITEM_HEIGHT - 1

        candidates = [
            border
            for border in borders[i + 1 :]
            if abs(border - expected_bottom) <= BORDER_HEIGHT_TOLERANCE
        ]

        if not candidates:
            continue

        bottom = min(
            candidates,
            key=lambda border: abs(border - expected_bottom),
        )

        height = bottom - top + 1

        if abs(height - ITEM_HEIGHT) > BORDER_HEIGHT_TOLERANCE:
            continue

        if top < SCAN_START_Y or bottom > grid_bottom:
            continue

        boxes.append(
            {
                "top": top,
                "bottom": bottom,
                "height": height,
            }
        )

    unique_boxes = []

    for box in sorted(boxes, key=lambda b: b["top"]):
        if (
            not unique_boxes
            or abs(box["top"] - unique_boxes[-1]["top"]) > BORDER_HEIGHT_TOLERANCE
        ):
            unique_boxes.append(box)

    return sorted(
        unique_boxes,
        key=lambda box: box["bottom"],
        reverse=True,
    )


def box_is_occupied(image, box):
    pixels = image.load()

    for y in range(
        box["top"] + BORDER_WIDTH,
        box["bottom"] - BORDER_WIDTH + 1,
    ):
        if pixels[SCAN_X, y][:3] == BANNER_COLOR[:3]:
            return True

    return False


def find_lowest_complete_box(image):
    boxes = detect_complete_boxes(image)

    if not boxes:
        return None

    box = boxes[0].copy()
    box["occupied"] = box_is_occupied(image, box)

    return box


def find_grid_top_border(image, y_start, y_end, scan_x=SCAN_X):
    y_start = max(1, y_start)
    y_end = min(y_end, image.height - 2)

    if not 0 <= scan_x < image.width:
        return None

    for y in range(y_start, y_end):
        if is_border(image, scan_x, y) and is_border(image, scan_x, y + 1):
            return y

    return None


def find_grid_banner(image, y_start, y_end):
    y_start = max(0, y_start)
    y_end = min(y_end, image.height)

    if y_start >= y_end:
        return None

    pixels = image.load()
    banner_run = 0
    expected = BANNER_COLOR[:3]

    for y in range(y_start, y_end):
        if pixels[SCAN_X, y][:3] == expected:
            banner_run += 1

            if banner_run >= ROW_BANNER_MIN_RUN:
                return y - banner_run + 1
        else:
            banner_run = 0

    return None


def has_exact_banner_at_expected_offset(
    image,
    top,
    scan_x=SCAN_X,
    icon_height=96,
    banner_height=BANNER_HEIGHT,
):
    banner_start = top + icon_height
    banner_end = banner_start + banner_height

    if banner_start < 0 or banner_end > image.height or not 0 <= scan_x < image.width:
        return False

    pixels = image.load()
    expected = BANNER_COLOR[:3]

    for y in range(banner_start, banner_end):
        if pixels[scan_x, y][:3] != expected:
            return False

    return True


def has_bottom_border_at_expected_offset(
    image,
    top,
    scan_x=SCAN_X,
    item_height=ITEM_HEIGHT,
):
    expected_bottom = top + item_height - BORDER_WIDTH

    candidates = find_border_candidates(
        image,
        scan_x,
        expected_bottom - BORDER_HEIGHT_TOLERANCE,
        expected_bottom + BORDER_HEIGHT_TOLERANCE + 1,
    )

    return any(
        abs(candidate - expected_bottom) <= BORDER_HEIGHT_TOLERANCE
        for candidate in candidates
    )


def find_grid_top_and_banner(image, y_start, y_end, config=None):
    if config is None:
        config = GRID_CONFIGS["stash"]

    scan_x = config["scan_x"]
    icon_height = config["icon_height"]
    item_height = config["item_height"]
    banner_height = config["banner_height"]

    top = find_grid_top_border(
        image,
        y_start,
        y_end,
        scan_x=scan_x,
    )

    if top is None:
        return None, None

    # Validate the row skeleton independently of the banner.
    if not has_bottom_border_at_expected_offset(
        image,
        top,
        scan_x=scan_x,
        item_height=item_height,
    ):
        return top, None

    # Player inventory rows may be valid even when the first slot is empty.
    if not has_exact_banner_at_expected_offset(
        image,
        top,
        scan_x=scan_x,
        icon_height=icon_height,
        banner_height=banner_height,
    ):
        return top, None

    banner_y = top + icon_height
    return top, banner_y


def detect_grid_rows(image, config=None, allow_empty_banner=False):
    if config is None:
        config = GRID_CONFIGS["stash"]

    scan_x = config["scan_x"]
    scan_top = max(0, config["start_y"])
    scan_bottom = min(config["bottom_y"], image.height)
    item_height = config["item_height"]

    if scan_bottom <= scan_top or not 0 <= scan_x < image.width:
        return []

    rows = []
    scan_y = scan_top

    while scan_y + item_height <= scan_bottom:
        top, banner_y = find_grid_top_and_banner(
            image,
            scan_y,
            scan_bottom,
            config=config,
        )

        if top is None:
            break

        if top <= scan_top:
            scan_y = top + ROW_BORDER_MAX_RUN + 1
            continue

        # Stash rows require a banner. Player inventory rows can be
        # scanned when their skeleton exists without a banner.
        if banner_y is None and not allow_empty_banner:
            scan_y = top + ROW_BORDER_MAX_RUN + 1
            continue

        rows.append(
            {
                "top": top,
                "bottom": top + item_height - 1,
            }
        )

        scan_y = top + item_height

    print(f"Detected {len(rows)} grid row(s).")
    return rows


def has_item_banner(image, row_top, column_x, config=None):
    """Check whether a slot appears occupied using its banner color.

    Sample 30 vertical pixels at the slot's horizontal center, immediately
    above the bottom border. At least 10 exact BANNER_COLOR matches mean
    the slot is considered occupied.
    """
    if config is None:
        config = GRID_CONFIGS["stash"]

    scan_x = column_x + config["item_width"] // 2
    sample_length = 30
    required_matches = 10

    # The bottom border is the last BORDER_WIDTH pixels of the slot.
    sample_bottom = row_top + config["item_height"] - BORDER_WIDTH
    sample_top = sample_bottom - sample_length

    if (
        scan_x < 0
        or scan_x >= image.width
        or sample_top < 0
        or sample_bottom > image.height
    ):
        return False

    pixels = image.load()
    expected = BANNER_COLOR[:3]
    matches = 0

    for y in range(sample_top, sample_bottom):
        if pixels[scan_x, y][:3] == expected:
            matches += 1

            if matches >= required_matches:
                return True

    return False


def detect_scrollbar(image):
    if not 0 <= SCROLLBAR_X < image.width:
        return None

    start_y = max(0, SCROLLBAR_START_Y)
    end_y = min(SCROLLBAR_END_Y, image.height - 1)

    if start_y > end_y:
        return None

    pixels = np.asarray(image.convert("RGB"))

    strip = pixels[
        start_y : end_y + 1,
        SCROLLBAR_X,
        :,
    ]

    accepted_colors = np.array(SCROLLBAR_COLORS, dtype=np.uint8)

    matches = np.any(
        np.all(
            strip[:, np.newaxis, :] == accepted_colors[np.newaxis, :, :],
            axis=2,
        ),
        axis=1,
    )

    transitions = np.diff(np.concatenate(([False], matches, [False])).astype(np.int8))

    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)

    if len(starts) == 0:
        return None

    longest = int(np.argmax(ends - starts))

    top = start_y + int(starts[longest])
    bottom = start_y + int(ends[longest]) - 1

    return top, bottom


def load_templates(
    template_dir,
    item_width,
    item_height,
    icon_height,
    template_extensions,
    structural_similarity,
    set_status,
):
    templates = []

    if structural_similarity is None:
        message = "Recognition unavailable. Install scikit-image."
        print(message)
        set_status(message)
        return templates

    if not os.path.isdir(template_dir):
        message = f"Template directory not found: {template_dir}"
        print(message)
        set_status(message)
        return templates

    for filename in sorted(os.listdir(template_dir)):
        if not filename.lower().endswith(template_extensions):
            continue

        filepath = os.path.join(template_dir, filename)

        try:
            with Image.open(filepath) as source:
                template_image = source.convert("RGB").resize(
                    (item_width, item_height),
                    Image.Resampling.LANCZOS,
                )

            template_array = np.asarray(
                template_image.crop((0, 0, item_width, icon_height)),
                dtype=np.uint8,
            )

            templates.append(
                {
                    "name": os.path.splitext(filename)[0],
                    "image": template_array,
                }
            )

        except Exception as exc:
            print(f"Failed to load template '{filename}': {exc}")

    message = f"Loaded {len(templates)} recognition template(s)."
    print(message)
    set_status(message)

    return templates


def estimate_items_moved(stack_size):
    if stack_size <= 0:
        return 0
    return 1 if stack_size == 1 else stack_size // 2


def build_player_loadout(main_items, quickuse_items):
    def aggregate_items(items):
        aggregated = {}

        for item in items:
            name = str(item.get("name", "")).strip()

            if not name or name.casefold() == "empty":
                continue

            try:
                quantity = int(str(item.get("banner_text")).strip())
            except (TypeError, ValueError):
                quantity = 1

            if quantity <= 0:
                continue

            aggregated[name] = aggregated.get(name, 0) + quantity

        return aggregated

    combined = aggregate_items(main_items)

    for name, quantity in aggregate_items(quickuse_items).items():
        combined[name] = combined.get(name, 0) + quantity

    return combined


def log_template_matches(
    image,
    rows,
    scan_number,
    phase,
    folder_path,
    templates,
    observation_lock,
    recognized_observations,
    recognize_row_slots,
):
    if phase != "up" or not templates:
        return

    log_path = os.path.join(folder_path, "recognition_log.txt")

    try:
        log_file = open(log_path, "w", encoding="utf-8")
    except Exception as exc:
        print(f"Could not create recognition log: {exc}")
        log_file = None

    scan_observations = []

    try:
        for row in rows:
            row_observations = recognize_row_slots(
                image,
                row,
                scan_number,
                phase,
            )

            scan_observations.extend(row_observations)

            if log_file is not None:
                for observation in row_observations:
                    log_file.write(
                        f"{observation['name']} | "
                        f"SSIM={observation['score']:.2f}% | "
                        f"row Y={observation['row_top']} | "
                        f"slot={observation['slot_index']}\\n"
                    )

        with observation_lock:
            recognized_observations.extend(scan_observations)

    finally:
        if log_file is not None:
            log_file.close()
