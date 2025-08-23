from typing import Iterable, Callable, TypeVar
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
from os import makedirs
from shutil import rmtree

from Components.config import config

from .Variables import EMBY_THUMB_CACHE_DIR


def convert_ticks_to_time(ticks, is_chapters=False):
    seconds_total = ticks / 10_000_000
    minutes = int(seconds_total // 60)
    hours = int(minutes // 60)
    minutes = int(minutes % 60)
    seconds = int(seconds_total % 60)
    if is_chapters:
        if hours == 0:
            return f"{minutes}:{seconds:02d}"
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    if hours == 0:
        return f"{minutes}min"
    return f"{hours}h {minutes}min"


def embyDateToString(dateString, type):
    cleaned_date = dateString.rstrip('Z')[:26]
    dt = datetime.fromisoformat(cleaned_date)

    if type == "Episode":
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%Y")


def embyEndsAtToString(totalTicks, positionTicks):
    if not totalTicks:
        return ""
    remainingSecs = (totalTicks - positionTicks) / 10_000_000
    end_time = datetime.now() + timedelta(seconds=remainingSecs)
    return _("Ends at") + " " + end_time.strftime("%H:%M")


def crop_image_from_bytes(image_bytes, target_width, target_height, dest_file):
    with Image.open(BytesIO(image_bytes)) as img:
        # Center crop to exact dimensions
        left = (img.width - target_width) / 2
        top = (img.height - target_height) / 2
        right = (img.width + target_width) / 2
        bottom = (img.height + target_height) / 2

        cropped_img = img.crop((left, top, right, bottom))

        cropped_img.save(dest_file, format='JPEG')


def resize_and_center_image(image_bytes, target_size, dest_file, background_color=(0, 0, 0)):
    # Open image
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    original_width, original_height = img.size
    target_width, target_height = target_size

    # Calculate scaling factor
    ratio = min(target_width / original_width, target_height / original_height)
    new_size = (int(original_width * ratio), int(original_height * ratio))

    # Resize using anti-aliasing
    resized_img = img.resize(new_size, Image.LANCZOS)

    # Create background
    background = Image.new("RGBA", target_size, background_color + (255,))

    # Compute position to center the resized image
    x = (target_width - new_size[0]) // 2
    y = (target_height - new_size[1]) // 2

    # Paste resized image onto background
    background.paste(resized_img, (x, y), resized_img)

    # Convert to RGB if you don't need alpha
    background.convert("RGB").save(dest_file, format='JPEG')


def insert_at_position(d, key, value, index):
    # Ensure index is within bounds
    index = max(0, min(index, len(d)))
    # Build a new dict in desired order
    items = list(d.items())
    items.insert(index, (key, value))
    return dict(items)


T = TypeVar('T')


def find_index(items: Iterable[T], predicate: Callable[[T], bool], default: int = -1) -> int:
    return next((i for i, x in enumerate(items) if predicate(x)), default)


def create_thumb_cache_dir(widget_id):
    if config.plugins.e2embyclient.thumbcache_loc.value == "off":
        return
    elif config.plugins.e2embyclient.thumbcache_loc.value == "/tmp":
        makedirs(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{widget_id}", exist_ok=True)
    else:
        makedirs(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}", exist_ok=True)


def delete_thumb_cache_dir(widget_id):
    if config.plugins.e2embyclient.thumbcache_loc.value == "off" or config.plugins.e2embyclient.thumbcache_loc.value == "/tmp":
        rmtree(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{widget_id}", ignore_errors=True)
