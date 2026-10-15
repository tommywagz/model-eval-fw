"""Backward-compatibility shim redirecting benchmaxxer imports to devbench."""

import sys
import devbench

sys.modules["benchmaxxer"] = devbench
for attr in dir(devbench):
    if not attr.startswith("__"):
        globals()[attr] = getattr(devbench, attr)
