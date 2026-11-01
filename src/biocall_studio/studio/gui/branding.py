"""Packaged suite identity for native Qt surfaces."""

from importlib.resources import files

from PySide6.QtGui import QIcon, QPixmap


def application_icon() -> QIcon:
    icon_bytes = files("biocall_studio.resources.branding").joinpath("icon-256.png").read_bytes()
    pixmap = QPixmap()
    if not pixmap.loadFromData(icon_bytes, "PNG"):
        raise RuntimeError("Bundled BioCall Studio icon could not be loaded.")
    return QIcon(pixmap)
