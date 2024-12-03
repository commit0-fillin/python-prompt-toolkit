from __future__ import annotations
import os
from enum import Enum
__all__ = ['ColorDepth']

class ColorDepth(str, Enum):
    """
    Possible color depth values for the output.
    """
    value: str
    DEPTH_1_BIT = 'DEPTH_1_BIT'
    DEPTH_4_BIT = 'DEPTH_4_BIT'
    DEPTH_8_BIT = 'DEPTH_8_BIT'
    DEPTH_24_BIT = 'DEPTH_24_BIT'
    MONOCHROME = DEPTH_1_BIT
    ANSI_COLORS_ONLY = DEPTH_4_BIT
    DEFAULT = DEPTH_8_BIT
    TRUE_COLOR = DEPTH_24_BIT

    @classmethod
    def from_env(cls) -> ColorDepth | None:
        """
        Return the color depth if the $PROMPT_TOOLKIT_COLOR_DEPTH environment
        variable has been set.

        This is a way to enforce a certain color depth in all prompt_toolkit
        applications.
        """
        color_depth = os.environ.get('PROMPT_TOOLKIT_COLOR_DEPTH')
        if color_depth:
            try:
                return cls(color_depth)
            except ValueError:
                # If the value is not a valid ColorDepth, return None
                return None
        return None

    @classmethod
    def default(cls) -> ColorDepth:
        """
        Return the default color depth for the default output.
        """
        # First, check if there's a value set in the environment
        env_depth = cls.from_env()
        if env_depth is not None:
            return env_depth

        # If not set in the environment, return the DEFAULT value
        return cls.DEFAULT
