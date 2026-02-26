"""Tool definitions for Gemini Agent function calling.

Maps device operations to OpenAI-compatible tool schemas.
Coordinates use 0-1000 relative scale (same as GLM agent).
"""

DEVICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tap",
            "description": "Tap at a point on the screen. Coordinates are relative (0-1000 scale).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_tap",
            "description": "Double tap at a point on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "long_press",
            "description": "Long press at a point on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swipe",
            "description": "Swipe from one point to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {
                        "type": "integer",
                        "description": "Start X (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "start_y": {
                        "type": "integer",
                        "description": "Start Y (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "end_x": {
                        "type": "integer",
                        "description": "End X (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                    "end_y": {
                        "type": "integer",
                        "description": "End Y (0-1000)",
                        "minimum": 0,
                        "maximum": 1000,
                    },
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused input field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch an app by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "App name"},
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "back",
            "description": "Press the Back button.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "home",
            "description": "Press the Home button.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for a duration before next action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "e.g. '2 seconds'"},
                },
                "required": ["duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Task completed. Call when the user's goal is achieved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Summary of result"},
                },
                "required": ["message"],
            },
        },
    },
]
