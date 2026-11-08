"""Train access to the suite-owned BioCall Studio brand resource."""

from importlib.resources import files

from PySide6.QtGui import QIcon, QPixmap


def application_icon() -> QIcon:
    """Load the packaged suite icon without a checkout-relative path."""
    icon_bytes = files("biocall_studio.resources.branding").joinpath("icon-256.png").read_bytes()
    pixmap = QPixmap()
    if not pixmap.loadFromData(icon_bytes, "PNG"):
        raise RuntimeError("Bundled BioCall Studio icon could not be loaded.")
    return QIcon(pixmap)
