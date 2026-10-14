from pathlib import Path
from PIL import Image

# Folder configuration
STASH_DIR = Path("stashes_big")
OUTPUT_DIR = Path("templates_big")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# Fixed crop boxes: (startX, startY, endX, endY)
BOXES = {
    "box1": (923, 363, 1115, 491),
    "box2": (1136, 363, 1328, 491),
}


def crop_image(image_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        for name, box in BOXES.items():
            crop = image.crop(box)
            crop.save(output_dir / f"{name}.png")


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
        print(f"No images found in {STASH_DIR.resolve()}")
        return

    print(f"Found {len(stash_files)} image(s).")

    successful = 0

    for stash_file in stash_files:
        print(f"Processing: {stash_file.name}")

        # Each source image gets its own output folder.
        output_dir = OUTPUT_DIR / stash_file.stem

        try:
            crop_image(stash_file, output_dir)
            successful += 1
        except Exception as error:
            print(f"Error processing {stash_file.name}: {error}")

    print(f"\nFinished! Processed {successful}/{len(stash_files)} image(s).")


if __name__ == "__main__":
    main()
