"""Bundled BioCall Studio Train identity for native Qt surfaces."""

from importlib.resources import files

from PySide6.QtGui import QIcon, QPixmap


def application_icon() -> QIcon:
    """Load the packaged high-resolution Train icon without a checkout-relative path."""
    icon_bytes = (
        files("biocall_studio_train.resources.branding")
        .joinpath("icon-256.png")
        .read_bytes()
    )
    pixmap = QPixmap()
    if not pixmap.loadFromData(icon_bytes, "PNG"):
        raise RuntimeError("Bundled BioCall Studio Train icon could not be loaded.")
    return QIcon(pixmap)
