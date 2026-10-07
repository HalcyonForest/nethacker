from __future__ import annotations

import importlib
import json
import os
import tempfile
from pathlib import Path

_cache_root = Path(tempfile.gettempdir()) / "nethack_arena_submission_cache"
_cache_root.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_cache_root / "xdg"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(_cache_root / "numba"))

import roles  # noqa: E402

# One modern main engine for all67 non-Healer/Samurai identities.
# Preserve the parent six Healer/Samurai specialist routes exactly.
SPECIALISTS = {'hea-gno-neu-fem': 'adapter_pf_vlom_9ef4063', 'hea-gno-neu-mal': 'adapter_pf_vlom_9ef4063', 'hea-hum-neu-fem': 'adapter_pf_hh', 'hea-hum-neu-mal': 'adapter_pf_vlom_8b492ce', 'sam-hum-law-fem': 'adapter_pf_v37', 'sam-hum-law-mal': 'adapter_pf_vk_s25'}

# Uniform transfer policy disables all legacy per-identity engine choices.
LEGACY = {}
_LEGACY_TABLES = {
    "v2": ({"hea-gno": "adapter_pf_hg", "hea-hum": "adapter_pf_hh", "pri-hum": "adapter_pf_pa", "sam": "adapter_pf_v35"},
           "adapter_nhbot_v2"),
    "v3": ({"hea-gno": "adapter_pf_hg", "hea-hum": "adapter_pf_hh", "sam": "adapter_pf_v35"}, "adapter_nhbot_v3"),
}


def _lookup(table, ident):
    if not ident:
        return None
    for prefix in sorted(table, key=len, reverse=True):
        if ident == prefix or ident.startswith(prefix + "-"):
            return table[prefix] or None
    return None


def route(ident, pre_ident):
    """(engine module, apply roles config?) for the identity; pre_ident = the identity read before any ^X probe."""
    src = LEGACY.get(ident) if ident and not os.environ.get("NHBOT_ROUTE") else None
    if src is not None:
        table, default = _LEGACY_TABLES[src]
        return _lookup(table, pre_ident) or default, False
    module_name = _specialist(ident) or "adapter"
    return module_name, module_name == "adapter"


def _specialist(ident):
    if not ident or os.environ.get("NHBOT_NO_SPECIALISTS"):
        return None
    table = dict(SPECIALISTS)
    # dev runs: NHBOT_ROUTE='{"tou": "adapter_pf_v25"}' (an empty name routes to nhbot)
    if os.environ.get("NHBOT_ROUTE"):
        import json
        table.update(json.loads(os.environ["NHBOT_ROUTE"]))
    for prefix in sorted(table, key=len, reverse=True):
        if ident == prefix or ident.startswith(prefix + "-"):
            return table[prefix] or None
    return None


class Bot:
    """Routes each identity to an engine: nhbot (an AutoAscend descendant) or a specialist."""

    def __init__(self) -> None:
        self._drivers = {}
        self._driver = None
        self._trace_file = None
        self._trace_step = 0

    def _get(self, module_name):
        if module_name not in self._drivers:
            self._drivers[module_name] = importlib.import_module(module_name).AutoAscendDriver()
        return self._drivers[module_name]

    def reset(self, initial_observation):
        trace_dir = os.environ.get("TRACE_OBS_DIR")
        if trace_dir:
            try:
                Path(trace_dir).mkdir(parents=True, exist_ok=True)
                episode = os.environ.get("JF_EPISODE", str(os.getpid()))
                self._trace_file = open(Path(trace_dir) / f"obs_{episode}.jsonl", "w", buffering=1)
            except OSError:
                self._trace_file = None
        ident = None
        try:
            ident = roles.identity(initial_observation)
        except Exception:  # noqa: BLE001
            pass
        # a role-only identity means the welcome line was not seen: ask ^X before choosing the engine
        self._probe = 0 if ident is None or ident.count("-") != 3 else None
        self._probe_ident = ident
        self._pre_ident = ident
        if self._probe is None:
            self._start(initial_observation, ident)

    def _start(self, initial_observation, ident):
        module_name, apply_roles = route(ident, getattr(self, "_pre_ident", ident))
        if apply_roles:
            try:
                roles.apply(ident)
            except Exception:  # noqa: BLE001 -- a bad override must never cost the episode
                pass
        self._driver = self._get(module_name)
        self._driver.reset(initial_observation)

    def act(self, observation):
        action = self._act(observation)
        self._trace_observation(observation, action)
        return action

    def _act(self, observation):
        if self._probe is not None:
            import nle.nethack as nh
            from nle.nethack import actions as A
            actions = tuple(nh.ACTIONS)
            if self._probe == 0:
                self._probe = 1
                return actions.index(A.Command.ATTRIBUTES)
            if self._probe == 1:
                try:
                    self._probe_ident = roles.attributes_identity(observation) or self._probe_ident
                except Exception:  # noqa: BLE001
                    pass
                self._probe = 2
                return actions.index(A.Command.ESC)
            self._probe = None
            self._start(observation, self._probe_ident)
        return self._driver.act(observation)

    def _trace_observation(self, observation, action):
        if self._trace_file is None:
            return
        try:
            message = bytes(observation["message"]).split(b"\0", 1)[0].decode("latin-1", "replace")
            screen = [bytes(row).decode("latin-1", "replace").rstrip("\0 ")
                      for row in observation["tty_chars"]]
            record = {
                "step": self._trace_step,
                "action": int(action),
                "message": message,
                "blstats": [int(x) for x in observation["blstats"]],
                "screen": screen,
            }
            self._trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._trace_step += 1
        except (OSError, KeyError, TypeError, ValueError):
            pass

    def close(self):
        for driver in self._drivers.values():
            driver.close()
        if self._trace_file is not None:
            self._trace_file.close()


def make_agent():
    return Bot()
