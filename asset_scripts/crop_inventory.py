
from pathlib import Path
from PIL import Image

# Folder configuration
STASH_DIR = Path("stashes")
OUTPUT_DIR = Path("templates")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# Grid configuration
START_X = 203
SCAN_X = 298
SCAN_START_Y = 350

ITEM_WIDTH = 128
ITEM_HEIGHT = 128

FIRST_COLUMN_GAP = 10
COLUMN_GAP = 11

ROWS = 6
COLUMNS = 4

BANNER_COLOR = (9, 12, 25)

# Border detection settings
BORDER_WIDTH = 2
MIN_BORDER_DISTANCE = 4


def color_distance(a, b):
    return sum(
        (int(a[i]) - int(b[i])) ** 2
        for i in range(3)
    ) ** 0.5


def is_banner(pixel):
    return tuple(pixel[:3]) == BANNER_COLOR


def is_border(image, x, y):
    """
    Detect a likely border pixel by comparing it with
    neighboring pixels on either side of the scan line.
    """
    pixels = image.load()

    if y < 1 or y + 1 >= image.height:
        return False

    current = pixels[x, y][:3]
    above = pixels[x, y - 1][:3]
    below = pixels[x, y + 1][:3]

    contrast_above = color_distance(current, above)
    contrast_below = color_distance(current, below)

    return (
        contrast_above >= MIN_BORDER_DISTANCE
        and contrast_below >= MIN_BORDER_DISTANCE
    )


def find_top_border(image, y_start):
    """Scan down until a likely top border is found."""
    for y in range(y_start, image.height - 1):
        if is_border(image, SCAN_X, y):
            if is_border(image, SCAN_X, y + 1):
                return y

    return None


def find_banner(image, y_start):
    """Find the exact banner color below the top border."""
    pixels = image.load()

    for y in range(y_start, image.height):
        if is_banner(pixels[SCAN_X, y]):
            return y

    return None


def find_bottom_border(image, banner_y):
    """Find the bottom border after the banner."""
    for y in range(banner_y + 1, image.height - 1):
        if is_border(image, SCAN_X, y):
            if is_border(image, SCAN_X, y + 1):
                return y

    return None


def detect_row_positions(image):
    rows = []
    scan_y = SCAN_START_Y

    for row in range(ROWS):
        top = find_top_border(image, scan_y)

        if top is None:
            print(f"Skipping row {row + 1}: top border not found")
            break

        banner_y = find_banner(image, top + BORDER_WIDTH)

        if banner_y is None:
            print(f"Skipping row {row + 1}: banner not found")
            scan_y = top + ITEM_HEIGHT
            continue

        bottom = find_bottom_border(image, banner_y)

        if bottom is None:
            print(f"Skipping row {row + 1}: bottom border not found")
            scan_y = top + ITEM_HEIGHT
            continue

        rows.append(top)

        print(
            f"Row {row + 1}: "
            f"top={top}, banner={banner_y}, bottom={bottom}, "
            f"height={bottom - top + 1}"
        )

        scan_y = bottom + 1

    return rows


def crop_inventory(screenshot_path, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with Image.open(screenshot_path) as original:
        image = original.convert("RGB")

        try:
            row_positions = detect_row_positions(image)

            for row, y in enumerate(row_positions):
                for col in range(COLUMNS):
                    x = START_X + col * ITEM_WIDTH

                    if col >= 1:
                        x += FIRST_COLUMN_GAP + (col - 1) * COLUMN_GAP

                    index = row * COLUMNS + col + 1

                    crop = image.crop((
                        x,
                        y,
                        x + ITEM_WIDTH,
                        y + ITEM_HEIGHT,
                    ))

                    crop.save(output / f"cell_{index:02}.png")

        finally:
            image.close()

    print(f"Saved inventory crops to {output.resolve()}")


def main():
    if not STASH_DIR.exists():
        print(f"Error: Stash folder not found: {STASH_DIR.resolve()}")
        return

    stash_files = sorted(
        file
        for file in STASH_DIR.iterdir()
        if file.is_file()
        and file.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not stash_files:
        print(f"No supported image files found in {STASH_DIR.resolve()}")
        return

    print(f"Found {len(stash_files)} stash image(s).")

    successful = 0

    for stash_file in stash_files:
        print(f"\n{'=' * 50}")
        print(f"Processing: {stash_file.name}")

        # Each screenshot gets its own output folder.
        stash_output = OUTPUT_DIR / stash_file.stem

        try:
            crop_inventory(stash_file, stash_output)
            successful += 1
        except Exception as error:
            print(f"Error processing {stash_file.name}: {error}")

    print(f"\nFinished! Processed {successful}/{len(stash_files)} stash image(s).")


if __name__ == "__main__":
    main()
