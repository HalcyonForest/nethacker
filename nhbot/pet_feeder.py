"""Offer plain food to a hunger-confused starting cat or dog.

Inspired by the parent's kni_steed.SteedKeeper. NetHack 3.6.6 dog.c accepts
plain food from a starving pet, and dothrow.c lets it land on the pet's square
even while confusion prevents an immediate catch.
"""

import re

import nle.nethack as nh

from . import utils
from .character import Character
from .glyph import G, MON
from .strategy import Strategy


PETS = frozenset(("kitten", "housecat", "large cat", "little dog", "dog", "large dog"))
PLAIN_FOOD = frozenset((
    "food ration", "cram ration", "lembas wafer", "tripe ration", "pancake",
    "candy bar", "apple", "carrot", "orange", "pear", "banana", "melon",
    "slime mold", "lump of royal jelly", "fortune cookie", "eucalyptus leaf",
))
PET_ATTACK = re.compile(r"\b(?:kitten|housecat|large cat|little dog|dog|large dog) "
                        r"(?:bites|claws|hits|kicks|butts)\b", re.IGNORECASE)


class HungryPetFeeder:
    def __init__(self, agent):
        self.agent = agent
        self.last_throw = -1000

    def _food(self):
        foods = [item for item in self.agent.inventory.items
                 if item.category == nh.FOOD_CLASS and len(item.objs) == 1 and
                 item.objs[0].name in PLAIN_FOOD and
                 getattr(item, "shop_status", 0) != 2]
        return min(foods, key=lambda item: item.objs[0].nutrition) if foods else None

    def _line_to(self, py, px):
        agent = self.agent
        y0, x0 = int(agent.blstats.y), int(agent.blstats.x)
        dy, dx = int(py) - y0, int(px) - x0
        distance = max(abs(dy), abs(dx))
        if distance < 1 or distance > 3 or not (dy == 0 or dx == 0 or abs(dy) == abs(dx)):
            return None
        sy, sx = int(dy > 0) - int(dy < 0), int(dx > 0) - int(dx < 0)
        level = agent.current_level()
        for k in range(1, distance):
            y, x = y0 + k * sy, x0 + k * sx
            glyph = agent.glyphs[y, x]
            if not level.walkable[y, x] or glyph in G.MONS or glyph in G.PETS or \
                    glyph in G.INVISIBLE_MON or glyph in G.BOULDER or \
                    level.objects[y, x] in G.DOOR_CLOSED:
                return None
        return sy, sx

    def _plan(self):
        agent = self.agent
        bl = agent.blstats
        # Role guard keeps the change scoped to the current Valkyrie objective.
        if agent.character.role != Character.VALKYRIE or \
                bl.time > agent._pet_starving_until or bl.time - self.last_throw < 5 or \
                agent.character.prop.hallu or agent.character.prop.blind or \
                agent.character.prop.confusion or agent.character.prop.stun:
            return None
        # A hunger message alone is not enough reason to spend the hero's last
        # ration. Feed only once the hungry pet has actually attacked us.
        if not PET_ATTACK.search(agent.message or ""):
            return None
        food = self._food()
        if food is None:
            return None
        y0, x0 = int(bl.y), int(bl.x)
        pets = []
        for y, x in zip(*utils.isin(agent.glyphs, G.PETS).nonzero()):
            if MON.permonst(agent.glyphs[y, x]).mname in PETS:
                pets.append((int(y), int(x)))
        for py, px in sorted(pets, key=lambda p: max(abs(p[0] - y0), abs(p[1] - x0))):
            direction = self._line_to(py, px)
            if direction is not None:
                return food, direction
        return None

    @Strategy.wrap
    def strategy(self):
        try:
            plan = self._plan()
        except Exception:
            plan = None
        if plan is None:
            yield False
            return
        yield True
        food, (dy, dx) = plan
        agent = self.agent
        self.last_throw = agent.blstats.time
        direction = agent.calc_direction(agent.blstats.y, agent.blstats.x,
                                         agent.blstats.y + dy, agent.blstats.x + dx)
        agent.log(f"PET feeding {food.objs[0].name} toward {direction}")
        agent.fire(food, direction)
