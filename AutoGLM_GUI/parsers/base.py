"""Base protocol for action parsers.

This module defines the interface that all action parsers must implement.
"""

from typing import Any, Protocol


class ActionParser(Protocol):
    """Protocol for parsing model outputs into action dictionaries.

    All parser implementations must provide:
    1. parse() method to convert raw model output into standardized action dict
    2. coordinate_scale property to specify the coordinate normalization range

    The standardized action dictionary format:
    {
        "_metadata": "do" | "finish",
        "action": "Tap" | "Swipe" | "Type" | ...,  # Only when _metadata="do"
        "coordinate": [x, y],  # Normalized to 0-1000 range
        "text": "...",  # For Type action
        ... # Other action-specific parameters
    }
    """

    def parse(self, raw_response: str) -> dict[str, Any]:
        """Parse raw model output into standardized action dictionary.

        Args:
            raw_response: Raw text output from the model.

        Returns:
            Standardized action dictionary with:
            - "_metadata": "do" or "finish"
            - "action": Action type (Tap, Swipe, etc.) when _metadata="do"
            - Additional parameters based on action type

        Raises:
            ValueError: If the response cannot be parsed.
        """
        ...

    @property
    def coordinate_scale(self) -> int:
        """Get the coordinate normalization scale used by this parser.

        Returns:
            999 for MAI parser, 1000 for GLM/PhoneAgent parsers.
        """
        ...
