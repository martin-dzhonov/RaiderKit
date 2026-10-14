from pathlib import Path
from math import sqrt
from PIL import Image

# ============================================================
# CONFIGURATION
# ============================================================

STASH_DIR = Path("player_stashes")
OUTPUT_DIR = Path("player_templates")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

ITEM_WIDTH = 128
ITEM_HEIGHT = 128

START_X = 1392
START_Y = 363

# Right boundary is exclusive for cropping.
LAST_COLUMN_RIGHT_X = 1936

# Bottom boundary is the last included pixel.
LAST_ROW_BOTTOM_Y = 767

SCAN_OFFSET = 30

MIN_GAP_RUN = 9
SIMILAR_COLOR_THRESHOLD = 12
DRAMATIC_CHANGE_THRESHOLD = 35
EDGE_SEARCH_TOLERANCE = 4

# Classification colors (RGB).
BANNER_COLOR = (9, 12, 25)
BACKGROUND_COLOR = (12, 15, 30)

# Classification tolerances.
BANNER_TOLERANCE = 3
BACKGROUND_TOLERANCE = 30
BORDER_DIFFERENCE = 35
GRADIENT_TOLERANCE = 12

# Bottom-center classification sample.
SAMPLE_WIDTH = 2
SAMPLE_HEIGHT = 5


# ============================================================
# COLOR HELPERS
# ============================================================


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


# ============================================================
# GRID DETECTION
# ============================================================


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

            print(
                f"  Candidate transition at {candidate}, "
                f"run={MIN_GAP_RUN}, change={change:.1f}"
            )

            if gap <= EDGE_SEARCH_TOLERANCE + MIN_GAP_RUN:
                print(f"  ACCEPTED edge={candidate}, gap={gap}px")
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

    print(f"\nDetecting {axis.upper()} positions")
    print(f"Start: {start}")
    print(f"Stop boundary: {stop}")
    print(f"Scan coordinate: {scan_coordinate}")

    while current + item_size < stop:
        print(
            f"\nSearching axis={axis}: current={current}, "
            f"expected next edge={current + item_size}, "
            f"scan line={scan_coordinate}"
        )

        next_position = find_next_box(
            image=image,
            current_position=current,
            stop_position=stop,
            scan_coordinate=scan_coordinate,
            axis=axis,
            item_size=item_size,
        )

        if next_position is None:
            print("No further box boundary detected.")
            break

        if next_position <= current:
            break

        # The bottom endpoint is inclusive, so a crop may end
        # exclusively at stop + 1.
        if next_position + item_size > stop + 1:
            print("Stopping: next box would exceed endpoint.")
            break

        positions.append(next_position)
        current = next_position
        print(f"Recorded position: {current}")

    print(f"Detected {axis} positions: {positions}")
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


# ============================================================
# BOX CLASSIFICATION
# ============================================================


def classify_box(image, x, y):
    """
    Inspect a 2x5 strip at the bottom center of a candidate box.

    ITEM:
        First 3 rows match the solid banner color.
        Last 2 rows differ from the banner.

    EMPTY:
        First 3 rows match the approximate background color.
        Last 2 rows differ from the background.

    NO_BOX:
        The sample has no recognizable banner/background-to-border
        transition.
    """

    center_x = x + ITEM_WIDTH // 2
    sample_left = center_x - SAMPLE_WIDTH // 2

    # Bottom-center sample: exactly 2 pixels wide x 5 pixels tall.
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

    # Average the two pixels in each row to reduce pixel noise.
    rows = [
        average_color(strip.getpixel((px, py)) for px in range(SAMPLE_WIDTH))
        for py in range(SAMPLE_HEIGHT)
    ]

    top_three = average_color(rows[:3])
    bottom_two = average_color(rows[3:])

    # 1. ITEM: banner color in the first three rows.
    banner_match = all(
        color_distance(row, BANNER_COLOR) <= BANNER_TOLERANCE for row in rows[:3]
    )

    if banner_match and color_distance(top_three, bottom_two) >= BORDER_DIFFERENCE:
        return "item"

    # 2. EMPTY: background color in the first three rows.
    background_match = all(
        color_distance(row, BACKGROUND_COLOR) <= BACKGROUND_TOLERANCE
        for row in rows[:3]
    )

    if background_match and color_distance(top_three, bottom_two) >= BORDER_DIFFERENCE:
        return "empty"

    # 3. NO BOX: all five rows have only small gradual changes.
    adjacent_differences = [
        color_distance(rows[i], rows[i + 1]) for i in range(SAMPLE_HEIGHT - 1)
    ]

    if all(difference <= GRADIENT_TOLERANCE for difference in adjacent_differences):
        return "no_box"

    # Unknown pattern: log the pixels to help tune thresholds.
    print(
        f"Uncertain sample at ({x}, {y}): "
        f"row_colors={rows}, "
        f"top={top_three}, bottom={bottom_two}"
    )

    return "no_box"


# ============================================================
# CROPPING AND SAVING
# ============================================================


def crop_inventory(image, column_positions, row_positions, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    cell_number = 1

    for y in row_positions:
        for x in column_positions:
            state = classify_box(image, x, y)

            crop = image.crop(
                (
                    x,
                    y,
                    x + ITEM_WIDTH,
                    y + ITEM_HEIGHT,
                )
            )

            output_path = output_dir / (f"cell_{cell_number:02d}_{state}_x{x}_y{y}.png")
            crop.save(output_path)

            print(f"Saved: {output_path} | " f"position=({x}, {y}) | type={state}")

            cell_number += 1


# ============================================================
# MAIN
# ============================================================


def main():
    if not STASH_DIR.exists():
        print(f"Input directory not found: {STASH_DIR}")
        return

    image_paths = sorted(
        path
        for path in STASH_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        print(f"No images found in {STASH_DIR}")
        return

    for image_path in image_paths:
        print("\n" + "=" * 60)
        print(f"Processing: {image_path.name}")
        print("=" * 60)

        with Image.open(image_path) as source:
            image = source.convert("RGB")

        column_positions, row_positions = detect_grid(image)

        output_dir = OUTPUT_DIR / image_path.stem

        crop_inventory(
            image=image,
            column_positions=column_positions,
            row_positions=row_positions,
            output_dir=output_dir,
        )

        print(
            f"\nFinished {image_path.name}: "
            f"{len(column_positions)} columns x "
            f"{len(row_positions)} rows"
        )


if __name__ == "__main__":
    main()
