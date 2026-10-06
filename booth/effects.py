
"""Effect packs -- the thing an over-the-air update replaces."""

import json
import logging

log = logging.getLogger(__name__)

BUILTIN = {
    "pack": "builtin",
    "version": "1.0.0",
    "effects": [
        {"id": "renaissance", "label": "Renaissance Portrait",
         "template": "renaissance"},
        {"id": "knight", "label": "Knight", "template": "knight"},
        {"id": "pharaoh", "label": "Pharaoh", "template": "pharaoh"},
    ],
}

REQUIRED = ("id", "label", "template")


class Effect:
    """One effect: a character portrait to place the visitor's face into."""

    __slots__ = ("id", "label", "template")

    def __init__(self, raw):
        self.id = str(raw["id"])
        self.label = str(raw["label"])
        self.template = str(raw["template"])


class EffectPack:
    def __init__(self, raw, source="builtin", error=None):
        self.name = str(raw.get("pack", "unnamed"))
        self.version = str(raw.get("version", "0.0.0"))
        self.source = source
        self.error = error
        self.effects = [Effect(e) for e in raw["effects"]]

    def __len__(self):
        return len(self.effects)

    def by_index(self, i):
        return self.effects[i % len(self.effects)]

    def describe(self):
        return f"{self.name} v{self.version}"


def _validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("pack is not an object")
    effects = raw.get("effects")
    if not isinstance(effects, list) or not effects:
        raise ValueError("pack has no effects")
    for i, e in enumerate(effects):
        if not isinstance(e, dict):
            raise ValueError(f"effect {i} is not an object")
        missing = [k for k in REQUIRED if not e.get(k)]
        if missing:
            raise ValueError(f"effect {i} missing {', '.join(missing)}")
    return raw


def load(path):
    """Load a pack, falling back to BUILTIN with the reason recorded."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = _validate(json.load(fh))
        pack = EffectPack(raw, source=path)
        log.info("loaded effect pack %s (%d effects) from %s",
                 pack.describe(), len(pack), path)
        return pack
    except FileNotFoundError:
        log.info("no pack at %s; using builtin", path)
        return EffectPack(BUILTIN)
    except Exception as exc:
        log.error("pack at %s rejected (%s); using builtin", path, exc)
        return EffectPack(BUILTIN, error=str(exc))
