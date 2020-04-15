"""Test requirements against Home Assistant."""
"""Copyright by @ludeeus"""

import warnings
import json
import requests

MANIFEST_FILE = "custom_components/sonos_alarm/manifest.json"


def test_requirement_versions():
    """Make sure HACS does not have a requirement that hass a different version from an integration in HA."""
    request = requests.get(
        "https://raw.githubusercontent.com/home-assistant/home-assistant/dev/requirements_all.txt"
    )
    requirements = {}
    for line in request.text.split("\n"):
        if "=" in line and not "#" in line:
            package = line.split(">")[0].split("=")[0]
            version = line.split("=")[-1]
            requirements[package] = version

    with open(MANIFEST_FILE, "r") as manifest_file:
        for line in json.loads(manifest_file.read())["requirements"]:
            package = line.split(">")[0].split("=")[0]
            version = line.split("=")[-1]
            if package in requirements:
                if version != requirements[package]:
                    warnings.warn(
                        "Package has different version from HA, this might casuse problems"
                    )


def test_requirement_in_ha_core():
    """Make sure HACS does not have a requirement that is part of HA core."""
    request = requests.get(
        "https://raw.githubusercontent.com/home-assistant/home-assistant/dev/setup.py"
    )
    res = request.text.split("REQUIRES = [")[-1].split("]")[0]
    requirements = {}
    for line in res.split("\n"):
        if "=" in line and not "#" in line:
            line = line.split('"')[1]
            package = line.split(">")[0].split("=")[0]
            version = line.split("=")[-1]
            requirements[package] = version

    with open(MANIFEST_FILE, "r") as manifest_file:
        for line in json.loads(manifest_file.read())["requirements"]:
            package = line.split(">")[0].split("=")[0]
            assert package not in requirements
