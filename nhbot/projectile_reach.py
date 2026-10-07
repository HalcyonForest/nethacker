"""Observable ordinary missile reach; unsupported contracts keep parent fallback."""
import nle.nethack as nh

THROWN = frozenset(('dagger', 'orcish dagger', 'elven dagger', 'silver dagger',
 'athame', 'worm tooth', 'knife', 'stiletto', 'scalpel', 'crysknife', 'dart', 'shuriken'))
BOWS = frozenset(('bow', 'elven bow', 'orcish bow', 'yumi'))
AMMO = frozenset(('arrow', 'elven arrow', 'orcish arrow', 'silver arrow', 'ya', 'crossbow bolt'))

def ordinary_reach(character, launcher, ammo):
    agent = character.agent
    bl = agent.blstats
    if character.prop.polymorph or bl.depth < 1:
        return None
    condition = int(agent.last_observation['blstats'][nh.NLE_BL_CONDITION])
    if condition & nh.BL_MASK_RIDE:
        return None
    level = agent.current_level()
    if (not level.walkable[bl.y, bl.x]
        or level.objects[bl.y, bl.x] in agent._wet_glyphs):
        return None  # submerged/unknown wet stance: preserve parent contract
    if (not ammo.is_unambiguous() or ammo.naming
        or ammo.object.name not in THROWN | AMMO):
        return None
    if launcher is None:
        if not ammo.is_thrown_projectile() or ammo.object.name not in THROWN:
            return None
    elif (not launcher.is_unambiguous() or launcher.naming
          or launcher.object.name not in BOWS | {'crossbow'}
          or not ammo.is_fired_projectile(launcher)):
        return None
    # NLE STR25 is the effective strength, despite the legacy field name.
    strength = int(bl.strength_percentage)
    weight = int(ammo.unit_weight())  # throwit splits one missile from the stack
    if not 3 <= strength <= 25 or weight < 0:
        return None
    crossbow = launcher is not None and launcher.object.name == 'crossbow'
    hero_range = (18 if crossbow else strength) // 2
    reach = max(1, hero_range - weight // 40)
    if launcher is not None:
        reach = 8 if crossbow else reach + 1
    if condition & nh.BL_MASK_LEV:
        reach = max(1, reach - max(1, hero_range - reach))
    return reach
