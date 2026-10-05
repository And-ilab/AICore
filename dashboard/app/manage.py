#!/usr/bin/env python
"""Совместимая точка входа для перенесенного Django backend."""
import os
import sys
from pathlib import Path


def main():
    backend = Path(__file__).resolve().parents[2] / "backend"
    backend_text = str(backend)
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    os.chdir(backend)
    os.environ["DJANGO_SETTINGS_MODULE"] = "sufler.settings"
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
