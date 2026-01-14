#!/usr/bin/env python3
"""Fix online field to state in test files."""

import sys

filenames = [
    "tests/integration/test_device_control.py",
    "tests/integration/test_config_management.py",
    "tests/integration/test_sse_streaming.py",
    "tests/integration/test_workflows.py",
]

for filename in filenames:
    try:
        with open(filename, "r") as f:
            content = f.read()

        if 'd["online"]' in content or 'mock_device["online"]' in content:
            content = content.replace('d["online"]', 'd["state"]')
            content = content.replace('mock_device["online"]', 'mock_device["state"]')

            with open(filename, "w") as f:
                f.write(content)
            print(f"Fixed: {filename}")
        else:
            print(f"No changes needed: {filename}")
    except FileNotFoundError:
        print(f"File not found: {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        sys.exit(1)

print("All files processed successfully")
