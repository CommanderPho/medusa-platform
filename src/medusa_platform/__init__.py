"""MEDUSA Platform — desktop application for real-time biosignal acquisition and apps."""

import importlib.metadata

from . import constants, exceptions

__version__ = importlib.metadata.version("MEDUSA-PLATFORM")
__all__ = ["__version__", "constants", "exceptions"]
