from math import sqrt
from PIL import Image

ITEM_WIDTH = 128
ITEM_HEIGHT = 128

START_X = 1392
START_Y = 363

LAST_COLUMN_RIGHT_X = 1936
LAST_ROW_BOTTOM_Y = 1183

SCAN_OFFSET = 30

MIN_GAP_RUN = 9
SIMILAR_COLOR_THRESHOLD = 12
DRAMATIC_CHANGE_THRESHOLD = 35
EDGE_SEARCH_TOLERANCE = 4

BANNER_COLOR = (9, 12, 25)
BACKGROUND_COLOR = (12, 15, 30)

BANNER_TOLERANCE = 3
BACKGROUND_TOLERANCE = 30
BORDER_DIFFERENCE = 35
GRADIENT_TOLERANCE = 12

SAMPLE_WIDTH = 2
SAMPLE_HEIGHT = 5


def color_distance(a, b):
    return sqrt(sum((int(a[i]) - int(b[i])) ** 2 for i in range(3)))


def average_color(pixels):
    pixels = list(pixels)

    if not pixels:
        return (0, 0, 0)

    return tuple(
        round(sum(pixel[channel] for pixel in pixels) / len(pixels))
        for channel in range(3)
    )


def find_next_box(
    image,
    current_position,
    stop_position,
    scan_coordinate,
    axis,
    item_size,
):
    expected_next = current_position + item_size

    search_start = expected_next
    search_end = min(
        expected_next + EDGE_SEARCH_TOLERANCE + MIN_GAP_RUN,
        stop_position,
    )

    if axis == "x":
        get_pixel = lambda p: image.getpixel((p, scan_coordinate))[:3]
    else:
        get_pixel = lambda p: image.getpixel((scan_coordinate, p))[:3]

    if search_start >= search_end:
        return None

    for candidate in range(
        search_start + MIN_GAP_RUN,
        search_end,
    ):
        run_start = candidate - MIN_GAP_RUN

        run_colors = [get_pixel(p) for p in range(run_start, candidate)]

        reference_color = average_color(run_colors)

        consistent_run = all(
            color_distance(color, reference_color) <= SIMILAR_COLOR_THRESHOLD
            for color in run_colors
        )

        if not consistent_run:
            continue

        new_color = get_pixel(candidate)
        change = color_distance(reference_color, new_color)

        if change >= DRAMATIC_CHANGE_THRESHOLD:
            gap = candidate - expected_next

            if gap <= EDGE_SEARCH_TOLERANCE + MIN_GAP_RUN:
                return candidate

    return None


def detect_axis_positions(
    image,
    start,
    stop,
    scan_coordinate,
    axis,
    item_size,
):
    positions = [start]
    current = start

    while current + item_size < stop:
        next_position = find_next_box(
            image=image,
            current_position=current,
            stop_position=stop,
            scan_coordinate=scan_coordinate,
            axis=axis,
            item_size=item_size,
        )

        if next_position is None:
            break

        if next_position <= current:
            break

        if next_position + item_size > stop + 1:
            break

        positions.append(next_position)
        current = next_position

    return positions


def detect_grid(image):
    horizontal_scan_y = START_Y + SCAN_OFFSET
    vertical_scan_x = START_X + SCAN_OFFSET

    column_positions = detect_axis_positions(
        image=image,
        start=START_X,
        stop=LAST_COLUMN_RIGHT_X,
        scan_coordinate=horizontal_scan_y,
        axis="x",
        item_size=ITEM_WIDTH,
    )

    row_positions = detect_axis_positions(
        image=image,
        start=START_Y,
        stop=LAST_ROW_BOTTOM_Y,
        scan_coordinate=vertical_scan_x,
        axis="y",
        item_size=ITEM_HEIGHT,
    )

    return column_positions, row_positions


def classify_box(image, x, y):
    center_x = x + ITEM_WIDTH // 2
    sample_left = center_x - SAMPLE_WIDTH // 2

    sample_top = y + ITEM_HEIGHT - SAMPLE_HEIGHT
    sample_bottom = y + ITEM_HEIGHT

    strip = image.crop(
        (
            sample_left,
            sample_top,
            sample_left + SAMPLE_WIDTH,
            sample_bottom,
        )
    ).convert("RGB")

    rows = [
        average_color(strip.getpixel((px, py)) for px in range(SAMPLE_WIDTH))
        for py in range(SAMPLE_HEIGHT)
    ]

    top_three = average_color(rows[:3])
    bottom_two = average_color(rows[3:])

    banner_match = all(
        color_distance(row, BANNER_COLOR) <= BANNER_TOLERANCE for row in rows[:3]
    )

    if banner_match and color_distance(top_three, bottom_two) >= BORDER_DIFFERENCE:
        return "item_box"

    background_match = all(
        color_distance(row, BACKGROUND_COLOR) <= BACKGROUND_TOLERANCE
        for row in rows[:3]
    )

    if background_match and color_distance(top_three, bottom_two) >= BORDER_DIFFERENCE:
        return "empty_box"

    adjacent_differences = [
        color_distance(rows[i], rows[i + 1]) for i in range(SAMPLE_HEIGHT - 1)
    ]

    if all(difference <= GRADIENT_TOLERANCE for difference in adjacent_differences):
        return "no_box"

    return "no_box"


def get_inventory_cells(image, column_positions, row_positions):
    cells = []

    for row_index, y in enumerate(row_positions):
        for column_index, x in enumerate(column_positions):
            status = classify_box(image, x, y)

            cells.append(
                {
                    "row_index": row_index,
                    "column_index": column_index,
                    "x": x,
                    "y": y,
                    "status": status,
                }
            )

    return cells


def scan_inventory(image):
    """
    Scan the supplied screenshot and return detected grid information.

    Args:
        image: PIL Image captured from the game screen.

    Returns:
        Dictionary containing grid dimensions, coordinates, and cell statuses.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("scan_inventory() expects a PIL Image object.")

    image = image.convert("RGB")

    column_positions, row_positions = detect_grid(image)

    cells = get_inventory_cells(
        image=image,
        column_positions=column_positions,
        row_positions=row_positions,
    )

    print(cells)

    return {
        "grid": {
            "rows": len(row_positions),
            "columns": len(column_positions),
            "column_positions": column_positions,
            "row_positions": row_positions,
        },
        "cells": cells,
    }
