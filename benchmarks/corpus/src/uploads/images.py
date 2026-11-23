"""Processing for pictures people attach to tasks."""

THUMB_SIZE = (320, 320)


def make_thumbnail(image):
    copy = image.copy()
    copy.thumbnail(THUMB_SIZE)
    return copy


def strip_metadata(image):
    """Drop EXIF before saving: it can include where the photo was taken and the camera serial."""
    clean = image.copy()
    clean.info.pop("exif", None)
    return clean
