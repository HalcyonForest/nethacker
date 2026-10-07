"""Observable ordinary melee valuation for inventory choice, without target state."""
from collections import Counter
from functools import lru_cache
import re

# Explicit ordinary direct-contact weapons. Polearms, jousting and weapon-tools
# keep the parent model; their action contracts differ from ordinary weapons.
ORDINARY = frozenset(('orcish dagger', 'dagger', 'silver dagger', 'athame',
 'elven dagger', 'worm tooth', 'knife', 'stiletto', 'scalpel', 'crysknife',
 'axe', 'battle-axe', 'orcish short sword', 'short sword', 'dwarvish short sword',
 'elven short sword', 'broadsword', 'runesword', 'elven broadsword', 'long sword',
 'katana', 'two-handed sword', 'tsurugi', 'scimitar', 'silver saber', 'club',
 'aklys', 'mace', 'morning star', 'flail', 'war hammer', 'quarterstaff',
 'orcish spear', 'spear', 'silver spear', 'elven spear', 'dwarvish spear',
 'javelin', 'trident', 'bullwhip', 'rubber hose'))

@lru_cache(maxsize=128)
def damage_distribution(expression):
    """Small bounded convolution of the parent's physical weapon dice."""
    distribution = Counter({0: 1})
    for term in expression.split('+'):
        match = re.fullmatch(r'(\d*)d(\d+)', term)
        if match:
            count, sides = int(match[1] or 1), int(match[2])
            if not 1 <= count <= 3 or not 1 <= sides <= 20:
                raise ValueError('Unsupported physical dice')
            for _ in range(count):
                next_distribution = Counter()
                for total, ways in distribution.items():
                    for roll in range(1, sides + 1):
                        next_distribution[total + roll] += ways
                distribution = next_distribution
        elif term.isdigit() and int(term) <= 20:
            distribution = Counter({total + int(term): ways for total, ways in distribution.items()})
        else:
            raise ValueError('Unsupported physical damage expression')
    return tuple(distribution.items())

def strength_damage(strength):
    # weapon.c dbon uses STR125, which the parent calls blstats.strength.
    return (-1 if strength < 6 else 0 if strength < 16 else 1 if strength < 18
            else 2 if strength == 18 else 3 if strength <= 93 else 4 if strength <= 108
            else 5 if strength < 118 else 6)

def ordinary_melee_bonus(character, item, large_monster, parent):
    """Return a calibrated observable proxy, or None to preserve the parent.

    No target AC, luck, armor/state, resistance, special hit, racial or artifact
    estimate is implied. Combat action-class priorities and wield flow remain.
    """
    if character.prop.polymorph or character.agent.inventory.items.off_hand is not None:
        return None
    skill_hit, skill_damage = character._get_weapon_skill_bonus(item)
    if item is None:
        expression = 'd4' if character.role in (character.MONK, character.SAMURAI) else 'd2'
        enchantment = 0
    else:
        if not item.is_weapon() or not item.is_unambiguous() or item.object.name not in ORDINARY:
            return None
        if item.modifier is None or item.naming or item.dmg_bonus is not None or item.to_hit_bonus is not None:
            return None
        if any(word in (item.text or '').lower() for word in
               ('rusty', 'corroded', 'burnt', 'rotted', 'poisoned')):
            return None
        enchantment = item.modifier
        expression = item.object.damage_large if large_monster else item.object.damage_small
        level = character.skill_levels[abs(item.object.sub)]
        if level <= character.SKILL_LEVEL_UNSKILLED:
            skill_damage = -2  # Parent weapon_bonus has the opposite sign.
    bl = character.agent.blstats
    hit = parent[0] - (item is not None) + (bl.experience_level < 3)
    if bl.carrying_capacity:
        hit -= 2 * bl.carrying_capacity - 1
    distribution = damage_distribution(expression)
    strength = strength_damage(bl.strength)
    total = ways_total = 0
    for roll, ways in distribution:
        # weapon.c dmgval clips an ordinary enchanted weapon to zero first.
        base = max(0, roll + enchantment)
        damage = base + (strength if base > 0 else 0) + (skill_damage if base > 1 else 0)
        # uhitm.c applies its final floor after strength and valid-attack skill.
        total += ways * max(1, damage)
        ways_total += ways
    return hit, total / ways_total
