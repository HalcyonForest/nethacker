"""Per-identity configuration: read the identity from the first observation, then override engine settings.

Overrides are module attributes of the nhbot engine, written as "module.NAME" (e.g. "dive_logic.DIVE_XL",
"jf_config.FORCE_BOLT"). Each episode runs in a fresh bot process, so setting them at reset() is safe.
Dev runs may add or replace overrides with JF_ROLE_CFG='{"wiz": {"dive_logic.EARLY_DIVE_XL": 4}}'; keys are
identity prefixes ("wiz", "wiz-elf", "wiz-elf-cha-mal"), applied from the least to the most specific;
"*" applies to every identity.
"""
from __future__ import annotations

import importlib
import json
import os
import re

# identity prefix -> {"module.NAME": value}
# Uniform transfer variant uses the current main engine defaults for every role.
OVERRIDES: dict[str, dict[str, object]] = {}

_ROLES = {"Archeologist": "arc", "Barbarian": "bar", "Caveman": "cav", "Cavewoman": "cav", "Healer": "hea",
          "Knight": "kni", "Monk": "mon", "Priest": "pri", "Priestess": "pri", "Ranger": "ran", "Rogue": "rog",
          "Samurai": "sam", "Tourist": "tou", "Valkyrie": "val", "Wizard": "wiz"}
_RACES = {"human": "hum", "elven": "elf", "dwarven": "dwa", "gnomish": "gno", "orcish": "orc"}
_ALIGNS = {"lawful": "law", "neutral": "neu", "chaotic": "cha"}
_FEMALE_ROLES = {"Cavewoman", "Priestess", "Valkyrie"}
_RE = re.compile(r"You are an? (lawful|neutral|chaotic) (?:(male|female) )?(human|elven|dwarven|gnomish|orcish) "
                 r"(" + "|".join(_ROLES) + r")\b")
_RE_CUT = re.compile(r"You are an? (lawful|neutral|chaotic) (?:(male|female) )?(human|elven|dwarven|gnomish|orcish)")
_RE_TITLE = re.compile(r"Agent the (\w+)")
# Xp 1 rank titles (role.c): the welcome line is cut at 80 columns for long role names
_TITLES = {"Digger": "Archeologist", "Plunderer": "Barbarian", "Plunderess": "Barbarian",
           "Troglodyte": "Caveman", "Rhizotomist": "Healer", "Gallant": "Knight", "Candidate": "Monk",
           "Aspirant": "Priest", "Tenderfoot": "Ranger", "Footpad": "Rogue", "Hatamoto": "Samurai",
           "Rambler": "Tourist", "Stripling": "Valkyrie", "Evoker": "Wizard"}

_RE_ATTRIBUTES = re.compile(r"You are an? [^,]+, a level \d+ (?:(male|female) )?(human|elven|dwarven|gnomish|orcish) "
                            r"(" + "|".join(_ROLES) + r")\.\s+You are (lawful|neutral|chaotic)\b")


def attributes_identity(observation) -> str | None:
    """Identity from the ^X attributes screen (background line + alignment line)."""
    try:
        text = bytes(observation["tty_chars"]).decode("latin-1", "replace")
    except Exception:  # noqa: BLE001
        return None
    m = _RE_ATTRIBUTES.search(text)
    if m is None:
        return None
    gender, race, role, align = m.groups()
    gender = "fem" if gender == "female" or role in _FEMALE_ROLES else "mal"
    return f"{_ROLES[role]}-{_RACES[race]}-{_ALIGNS[align]}-{gender}"


def identity(observation) -> str | None:
    texts = []
    for key in ("message", "tty_chars"):
        try:
            texts.append(bytes(observation[key]).decode("latin-1", "replace"))
        except Exception:  # noqa: BLE001
            pass
    text = " ".join(texts)
    m = _RE.search(text)
    if m is not None:
        align, gender, race, role = m.groups()
    else:
        m = _RE_CUT.search(text)
        t = _RE_TITLE.search(text)
        if m is None or t is None or t.group(1) not in _TITLES:
            t = _RE_TITLE.search(text)
            if t is None or t.group(1) not in _TITLES:
                return None
            return _ROLES[_TITLES[t.group(1)]]
        align, gender, race = m.groups()
        role = _TITLES[t.group(1)]
    gender = "fem" if gender == "female" or role in _FEMALE_ROLES else "mal"
    return f"{_ROLES[role]}-{_RACES[race]}-{_ALIGNS[align]}-{gender}"


def overrides_for(ident: str | None) -> dict[str, object]:
    table = {k: dict(v) for k, v in OVERRIDES.items()}
    raw = os.environ.get("JF_ROLE_CFG")
    if raw:
        for k, v in json.loads(raw).items():
            table.setdefault(k, {}).update(v)
    out: dict[str, object] = dict(table.get("*", {}))   # "*": every identity, before any prefix
    if not ident:
        return out
    for prefix in sorted((k for k in table if k != "*"), key=len):
        if ident == prefix or ident.startswith(prefix + "-"):
            out.update(table[prefix])
    return out


def apply(ident: str | None) -> dict[str, object]:
    applied = overrides_for(ident)
    for name, value in applied.items():
        mod, _, attr = name.rpartition(".")
        module = importlib.import_module(f"nhbot.{mod}")
        if not hasattr(module, attr):
            raise AttributeError(f"roles: nhbot.{mod} has no {attr}")
        if attr == "GRIND_LEVELS" and isinstance(value, dict):
            value = {int(k): int(v) for k, v in value.items()}
        if attr == "ROLE_GRIND_LEVELS" and isinstance(value, dict):
            value = {r: {int(k): int(v) for k, v in t.items()} for r, t in value.items()}
        setattr(module, attr, value)
    return applied
