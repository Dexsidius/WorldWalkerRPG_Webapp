"""Local, AI-cost-free combat resolver.

The rest of the engine (engine_turns.py) resolves every action — including
combat — through assess() + resolve(), each an AI call. That's fine for a
one-off action, but a fight is a *sequence* of exchanges, and paying for two
AI round-trips per swing makes combat slow and expensive without making it
more fun. This module resolves each exchange locally instead:

  1. The AI still decides when a fight starts and who's in it (as part of a
     normal resolve() call) — narrative judgment stays with the AI.
  2. Every subsequent round (attack/defend/flee) is resolved with plain
     Python: the SAME d100-vs-sampled-difficulty math engine_turns.roll()
     already uses, reusing the player's real stats/skills/titles, so a
     trained skill hits as hard here as it would narratively. No AI call,
     no wait, no cost.
  3. Only "relaying the results" costs anything: one AI call, made once
     (at combat's end, or on request), turns the accumulated mechanical
     log into narration and any loot/injury/consequence state_patch —
     exactly the existing resolve() contract, just fed a combat summary
     instead of a single action.

If the player does something the local engine can't model (negotiate,
improvise with the environment, a puzzle-boss mechanic), the frontend can
still fall back to a normal AI-costing take_turn() — that's a deliberate,
honest scope boundary, not a gap.
"""
import random

from worlds import DIFFICULTIES, abilities_for, primary_stats_for, ability_resource_type_for, speed_stat_for, defense_stat_for
from util import clamp
from systems import normalize_tuning

BASE_HIT_PCT = 0.13         # a bare-minimum successful hit does ~13% of the target's max HP
MARGIN_HIT_PCT = 0.09       # up to another 9% for a big margin over the difficulty
MARGIN_CAP = 60             # margin beyond this stops adding damage (avoids runaway one-shots)
SKILL_DAMAGE_SCALE = 50.0   # a skill_bonus of 50 roughly doubles damage dealt with it
BREAKTHROUGH_MULTIPLIER = 1.5
DEFEND_DAMAGE_REDUCTION = 0.5
MAX_ROUNDS_PER_CALL = 1     # resolve exactly one exchange per API call, so the UI can animate it

# A named ability spends real resource on every USE (hit or miss — you spent
# the chakra channeling the jutsu whether or not it landed), sized as a
# fraction of the player's own max pool so it scales with power level the
# same way damage does: a level-40 character with a 200-Chakra pool spends
# proportionally the same as a level-3 character with a 50-Chakra pool.
BASE_RESOURCE_COST_PCT = 0.15   # a plain named ability costs ~15% of max pool per use
SKILL_COST_SCALE = 150.0        # a skill_bonus of 30 adds ~20% more cost — a more mastered technique is a bigger spend
COOLDOWN_ROUNDS = 3             # cooldown-type abilities (e.g. Overgeared Skills) are unusable for this many rounds after use

# Raw stat-vs-power gaps (both on the same ~10-200 world-relative scale) that
# turn a real mismatch into a real tactical swing, instead of just a slightly
# better d100 bonus: a decisively faster combatant gets a bonus swing, a
# decisively harder-hitting one does drastically more damage, and a
# decisively tougher one can just shrug a hit off completely.
SPEED_GAP_THRESHOLD = 25         # player_speed - enemy_power (or the reverse) at/above this grants a bonus swing
MASSIVE_GAP_THRESHOLD = 30       # offense-vs-power gap at/above this triggers massive damage; the mirrored gap fully negates a hit
MASSIVE_DAMAGE_MULTIPLIER = 2.5

# A structured "overwhelm" action for canon instant-win-type abilities
# (Rimuru absorbing a foe, flaring Conqueror's Haki to drop weaker fighters,
# a hypnosis/domination effect, etc.) — same d100 math, just checked against
# a harder target than a normal hit unless the power gap already makes the
# outcome a foregone conclusion. Can be attempted every round, Pokéball-style
# — repeat attempts cost nothing extra locally, they just may not land.
OVERWHELM_DIFFICULTY_PADDING = 25


class CombatMixin:
    # ---------- setup / backfill ----------
    def ensure_combat_numbers(self):
        """Combat is always exactly player vs. one opposing entity — a
        single person, or a whole group represented as one aggregate (see
        gm_rules). The AI is asked to give that entity numeric
        difficulty_min/max, attack_min/max and power; if it ever
        under-specifies one (a smaller model skipping a field is common),
        fill it in from the player's own current stats so combat is always
        locally resolvable — never blocked on a malformed patch."""
        combat = self.state.get("combat")
        if not isinstance(combat, dict) or not combat.get("active"):
            return
        world = self.state.get("world", "Custom World")
        stats = self.state.get("stats", {}) or {}
        avg_stat = int(sum(stats.values()) / max(1, len(stats))) if stats else 30
        combat.setdefault("round", 1)
        combat.setdefault("player_defense_ability", (primary_stats_for(world, self.state.get("special", {}).get("Archetype", "")) or abilities_for(world))[0])

        # Backward compat: a save/in-flight fight from before combat became
        # strictly 1v1-or-1-group may still carry an old-style "enemies"
        # list. Collapse it into one aggregate opponent instead of breaking.
        if not combat.get("enemy") and combat.get("enemies"):
            legacy = [e for e in combat["enemies"] if isinstance(e, dict)]
            if legacy:
                combat["enemy"] = {
                    "name": legacy[0].get("name", "Enemy") if len(legacy) == 1 else f"{legacy[0].get('name', 'Enemy')} and allies",
                    "is_group": len(legacy) > 1, "group_size": len(legacy) if len(legacy) > 1 else None,
                    "hp": sum(int(e.get("hp", 0) or 0) for e in legacy),
                    "hp_max": sum(int(e.get("hp_max", 0) or 0) for e in legacy),
                    "power": int(sum(int(e.get("power", avg_stat) or avg_stat) for e in legacy) / len(legacy)),
                    "difficulty_min": min(int(e.get("difficulty_min", 30) or 30) for e in legacy),
                    "difficulty_max": max(int(e.get("difficulty_max", 50) or 50) for e in legacy),
                    "attack_min": min(int(e.get("attack_min", 25) or 25) for e in legacy),
                    "attack_max": max(int(e.get("attack_max", 45) or 45) for e in legacy),
                    "alive": True,
                }
            combat.pop("enemies", None)

        enemy = combat.get("enemy")
        if not isinstance(enemy, dict):
            enemy = {"name": "Enemy"}
            combat["enemy"] = enemy
        enemy.setdefault("alive", enemy.get("hp", 1) > 0)
        hp_max = int(enemy.get("hp_max") or enemy.get("hp") or max(20, avg_stat * 2))
        enemy["hp_max"] = hp_max
        enemy["hp"] = int(enemy.get("hp", hp_max))
        power = enemy.get("power")
        if power is None:
            power = clamp(avg_stat + random.randint(-8, 8), 10, 200)
        enemy["power"] = int(power)
        if enemy.get("difficulty_min") is None or enemy.get("difficulty_max") is None:
            center = clamp(int(enemy["power"] * 1.0), 15, 90)
            enemy["difficulty_min"], enemy["difficulty_max"] = clamp(center - 10, 1, 100), clamp(center + 10, 1, 100)
        if enemy.get("attack_min") is None or enemy.get("attack_max") is None:
            center = clamp(int(enemy["power"] * 0.9), 15, 90)
            enemy["attack_min"], enemy["attack_max"] = clamp(center - 10, 1, 100), clamp(center + 10, 1, 100)

        combat.setdefault("log", [])
        combat.setdefault("narrated_through", 0)
        combat.setdefault("outcome", None)
        combat.setdefault("cooldowns", {})
        combat.setdefault("ally_support", 0)
        combat.setdefault("enemy_debuffs", [])
        combat.setdefault("non_lethal", False)
        # Player-controlled, independent of combat.non_lethal: choosing to
        # spare a real, dangerous opponent only protects THEM from dying to
        # the player's own hits — it does nothing for the player's own HP.
        # Lose this fight and the enemy still kills you; this is mercy you
        # extend, not a safety net you get.
        combat.setdefault("spare_enemy", False)

    def combat_active(self):
        combat = self.state.get("combat")
        return isinstance(combat, dict) and bool(combat.get("active"))

    # ---------- shared d100 check (same shape as engine_turns.roll(), just parameterized) ----------
    def _combat_check(self, actor_bonus, difficulty_min, difficulty_max):
        shift = int(DIFFICULTIES[self.state["difficulty"]].get("difficulty_shift", 0))
        tuning = normalize_tuning(self.state)
        shift += int(round((tuning.get("combat_danger", 1.0) - 1.0) * 10))
        low, high = clamp(int(difficulty_min) + shift, 1, 100), clamp(int(difficulty_max) + shift, 1, 100)
        if low > high:
            low, high = high, low
        difficulty = random.randint(low, high)
        raw = random.randint(1, 100)
        breakthrough = raw >= 99
        total = raw + actor_bonus + (15 if breakthrough else 0)
        success = total > difficulty
        if raw == 1:
            success = False
        margin = max(0, total - difficulty)
        return {"roll": raw, "total": total, "difficulty": difficulty, "success": success,
                "margin": margin, "breakthrough": breakthrough}

    def _player_offense_bonus(self, ability, skill):
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        benchmark = 30
        stat_bonus = int(round((stat - benchmark) / 4.0))
        sb = self.skill_bonus(skill) if skill else 0
        tb = self.title_bonus()
        return stat_bonus + sb + tb, sb

    def _player_defense_bonus(self, combat):
        ability = combat.get("player_defense_ability") or abilities_for(self.state.get("world", "Custom World"))[0]
        stat = int(self.state.get("stats", {}).get(ability, 30) or 30)
        return int(round((stat - 30) / 4.0))

    def _damage(self, target_hp_max, margin, skill_bonus_used, breakthrough, massive=False):
        pct = BASE_HIT_PCT + (clamp(margin, 0, MARGIN_CAP) / MARGIN_CAP) * MARGIN_HIT_PCT
        multiplier = 1.0 + max(0, skill_bonus_used) / SKILL_DAMAGE_SCALE
        if breakthrough:
            multiplier *= BREAKTHROUGH_MULTIPLIER
        if massive:
            multiplier *= MASSIVE_DAMAGE_MULTIPLIER
        return max(1, round(target_hp_max * pct * multiplier))

    # ---------- resource / cooldown cost, and effect type, of a named ability ----------
    def _ability_resource_type(self, skill):
        """'pool' (spends the world resource — Chakra/Mana/Aura/Magicule/
        Stamina/Energy), 'cooldown' (no resource cost, but locked out for a
        few rounds), or 'free' (no cost at all). Honors an explicit
        resource_type on the skill if the GM set one (see gm_rules' skill
        authoring guidance), otherwise falls back to the world's default —
        this is what makes an untagged legacy skill still behave sensibly."""
        detail = self.state.get("skills", {}).get(skill) if skill else None
        explicit = str((detail or {}).get("resource_type", "")).strip().lower() if isinstance(detail, dict) else ""
        if explicit in ("pool", "cooldown", "free"):
            return explicit
        world = self.state.get("world", "Custom World")
        archetype = (self.state.get("special", {}) or {}).get("Archetype", "")
        return ability_resource_type_for(world, archetype)

    def _ability_resource_cost(self, skill_bonus_used):
        tuning = normalize_tuning(self.state)
        pct = BASE_RESOURCE_COST_PCT + max(0, skill_bonus_used) / SKILL_COST_SCALE
        pct *= float(tuning.get("resource_pressure", 1.0) or 1.0)
        resource_max = max(1, int(self.state.get("resource_max", 100) or 100))
        return max(1, round(resource_max * pct))

    def _ability_effect_type(self, skill):
        """'damage' (default — hits the opponent), 'heal' (restores the
        player's own HP), or 'debuff' (temporarily weakens the opponent).
        Set on the skill itself (see gm_rules); an untagged skill is always
        a damage effect, so nothing changes for existing skills."""
        detail = self.state.get("skills", {}).get(skill) if skill else None
        explicit = str((detail or {}).get("effect_type", "")).strip().lower() if isinstance(detail, dict) else ""
        return explicit if explicit in ("damage", "heal", "debuff") else "damage"

    def _effective_enemy_numbers(self, enemy, combat):
        """The enemy's combat numbers after active debuffs — power, hit
        difficulty and attack strength all scale down together while a
        debuff is live; hp/hp_max are never touched by this, only how
        dangerous and how hittable the opponent currently is."""
        debuff_pct = clamp(sum(float(d.get("power_pct", 0)) for d in combat.get("enemy_debuffs", [])), -0.6, 0.0)
        mult = 1.0 + debuff_pct
        return {
            "power": max(1, int(enemy["power"] * mult)),
            "difficulty_min": max(1, int(enemy["difficulty_min"] * mult)),
            "difficulty_max": max(1, int(enemy["difficulty_max"] * mult)),
            "attack_min": max(1, int(enemy["attack_min"] * mult)),
            "attack_max": max(1, int(enemy["attack_max"] * mult)),
        }

    # ---------- one swing of a named ability or plain attack ----------
    def _resolve_swing(self, combat, enemy, ability, swing_skill, resource_type, ally_support,
                        player_offense_stat_value, enemy_power, extra_swing):
        """Resolves exactly one use of an ability within a round — damage,
        heal, or debuff, whichever the selected ability actually is. Raises
        on the FIRST swing if the ability can't be paid for (blocks the
        whole action before anything happens); a bonus extra swing (from a
        decisive speed edge) that can't be paid for is simply skipped by the
        caller instead, since the first swing already landed."""
        bonus, sb_used = self._player_offense_bonus(ability, swing_skill)
        resource_cost = 0
        if swing_skill and resource_type == "cooldown":
            ready_at = combat["cooldowns"].get(swing_skill, 0)
            if combat["round"] < ready_at:
                raise RuntimeError(f"{swing_skill} is still recovering — usable again in {ready_at - combat['round']} more round(s).")
        elif swing_skill and resource_type == "pool":
            resource_cost = self._ability_resource_cost(sb_used)
            available = int(self.state.get("resource", 0) or 0)
            if resource_cost > available:
                raise RuntimeError(f"Not enough {self.state.get('resource_name', 'Energy')} to use {swing_skill} ({resource_cost} needed, {available} available).")

        effect_type = self._ability_effect_type(swing_skill) if swing_skill else "damage"
        eff = self._effective_enemy_numbers(enemy, combat)
        event = {"actor": "player", "ability": swing_skill or "Attack", "target": enemy["name"],
                  "resource_cost": resource_cost, "extra_swing": extra_swing, "effect": effect_type}

        if effect_type == "heal":
            # A reliability check, not an opposed one — you're not fighting
            # the enemy's stats to heal yourself, just executing correctly.
            check = self._combat_check(bonus, 20, 40)
            healed = 0
            if check["success"]:
                healed = self._damage(self.state.get("hp_max", 100), check["margin"], sb_used, check["breakthrough"])
                self.state["hp"] = min(int(self.state.get("hp_max", 100)), int(self.state.get("hp", 0)) + healed)
            event.update({"action": "heal", "healed": healed, **check})
        elif effect_type == "debuff":
            check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            applied = False
            if check["success"]:
                combat.setdefault("enemy_debuffs", []).append({"rounds_left": 3, "power_pct": -0.2})
                applied = True
            event.update({"action": "debuff", "applied": applied, **check})
        else:
            check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            massive = (player_offense_stat_value - enemy_power) >= MASSIVE_GAP_THRESHOLD
            shrugged = (enemy_power - player_offense_stat_value) >= MASSIVE_GAP_THRESHOLD
            dmg = 0
            if check["success"] and not shrugged:
                dmg = self._damage(enemy["hp_max"], check["margin"], sb_used, check["breakthrough"], massive)
                # The enemy is spared from actually dying either when this is
                # a non-lethal spar/test (floors both sides — see
                # resolve_combat_round) or when the player has personally
                # chosen to spare THIS opponent (combat.spare_enemy floors
                # only the enemy; it does nothing for the player's own HP).
                enemy_floor = 1 if (combat.get("non_lethal") or combat.get("spare_enemy")) else 0
                enemy["hp"] = max(enemy_floor, int(enemy["hp"]) - dmg)
                if enemy["hp"] <= enemy_floor:
                    enemy["alive"] = False
            event.update({"action": "attack", "damage": dmg, "massive": massive,
                          "shrugged": shrugged and check["success"], **check})

        if swing_skill and resource_type == "pool":
            self.state["resource"] = max(0, int(self.state.get("resource", 0)) - resource_cost)
        elif swing_skill and resource_type == "cooldown":
            combat["cooldowns"][swing_skill] = combat["round"] + COOLDOWN_ROUNDS
        return event

    # ---------- the actual round ----------
    def resolve_combat_round(self, action, ability_name=None):
        """One full exchange (player action, then the opponent's retaliation
        if it's still alive), resolved entirely locally. Always exactly
        player vs. the single combat.enemy entity — a lone foe or a whole
        group represented as one aggregate (see gm_rules). Returns a plain
        dict describing exactly what happened — no prose, no AI call."""
        self.ensure_combat_numbers()
        combat = self.state["combat"]
        enemy = combat.get("enemy") or {}
        # A spar, test, or supervised duel (combat.non_lethal) is won or lost
        # on points — HP is floored at 1 for both sides instead of 0, so
        # neither combatant can actually be killed by it.
        floor = 1 if combat.get("non_lethal") else 0
        if not enemy.get("alive", True) or int(enemy.get("hp", 0)) <= 0:
            return self.end_combat("victory")

        world = self.state.get("world", "Custom World")
        primary = primary_stats_for(world, self.state.get("special", {}).get("Archetype", "")) or [abilities_for(world)[0]]
        ability = primary[0]
        # Only applied when the GM judged this a coordinated group action
        # (an ambush, a party assault) — see gm_rules; 0 for any solo fight.
        ally_support = int(combat.get("ally_support", 0) or 0)
        enemy_power = int(enemy.get("power", 30) or 30)
        player_speed = int(self.state.get("stats", {}).get(speed_stat_for(world), 30) or 30)
        player_defense_stat_value = int(self.state.get("stats", {}).get(defense_stat_for(world), 30) or 30)
        player_offense_stat_value = int(self.state.get("stats", {}).get(ability, 30) or 30)
        events = []

        if action == "flee":
            bonus, _ = self._player_offense_bonus(ability, None)
            eff = self._effective_enemy_numbers(enemy, combat)
            check = self._combat_check(bonus + ally_support, eff["attack_min"], eff["attack_max"])
            if check["success"]:
                combat["log"].append({"round": combat["round"], "actor": "player", "action": "flee", **check, "result": "escaped"})
                return self.end_combat("fled")
            events.append({"actor": "player", "action": "flee", **check, "result": "failed to escape"})
        elif action == "defend":
            events.append({"actor": "player", "action": "defend", "result": "braced"})
        elif action == "overwhelm":
            # A canon instant-win-type move (absorption, Conqueror's Haki,
            # domination, ...) — same math, just a harder target unless the
            # power gap already makes the outcome a foregone conclusion.
            # Failing costs nothing but the attempt; try again next round.
            bonus, _ = self._player_offense_bonus(ability, ability_name if ability_name in self.state.get("skills", {}) else None)
            eff = self._effective_enemy_numbers(enemy, combat)
            gap = player_offense_stat_value - enemy_power
            if gap >= MASSIVE_GAP_THRESHOLD:
                check = self._combat_check(bonus + ally_support, eff["difficulty_min"], eff["difficulty_max"])
            else:
                check = self._combat_check(bonus + ally_support,
                                            eff["difficulty_min"] + OVERWHELM_DIFFICULTY_PADDING,
                                            eff["difficulty_max"] + OVERWHELM_DIFFICULTY_PADDING)
            events.append({"actor": "player", "action": "overwhelm", "ability": ability_name or "Overwhelm",
                            "target": enemy["name"], **check})
            if check["success"]:
                combat["log"].extend([{"round": combat["round"], **e} for e in events])
                return self.end_combat("overwhelmed")
        else:
            requested_skill = ability_name if ability_name and ability_name in self.state.get("skills", {}) else None
            requested_type = self._ability_resource_type(requested_skill) if requested_skill else "free"
            swings = 2 if (player_speed - enemy_power) >= SPEED_GAP_THRESHOLD else 1
            for swing_index in range(swings):
                if swing_index > 0 and requested_type == "cooldown":
                    # Can't reuse a move that its own first swing just put on
                    # cooldown; the bonus swing falls back to a plain attack.
                    swing_skill, resource_type = None, "free"
                else:
                    swing_skill, resource_type = requested_skill, requested_type
                try:
                    event = self._resolve_swing(combat, enemy, ability, swing_skill, resource_type, ally_support,
                                                 player_offense_stat_value, enemy_power, swing_index > 0)
                except RuntimeError:
                    if swing_index > 0:
                        break  # not enough left over for the bonus swing; the first swing's result still stands
                    raise
                events.append(event)
                if not enemy.get("alive", True):
                    break

        combat["log"].extend([{"round": combat["round"], **e} for e in events])

        if not enemy.get("alive", True):
            return self.end_combat("victory")

        if action != "flee":
            enemy_swings = 2 if (enemy_power - player_speed) >= SPEED_GAP_THRESHOLD else 1
            for swing_index in range(enemy_swings):
                eff = self._effective_enemy_numbers(enemy, combat)
                defense_bonus = self._player_defense_bonus(combat) + ally_support
                check = self._combat_check(int(eff["power"] * 0.35), eff["attack_min"], eff["attack_max"])
                # defense_bonus reduces the enemy's effective total by raising the threshold they must beat
                check["total"] -= defense_bonus
                check["success"] = check["total"] > check["difficulty"] and check["roll"] != 1
                massive = (enemy_power - player_defense_stat_value) >= MASSIVE_GAP_THRESHOLD
                shrugged = (player_defense_stat_value - enemy_power) >= MASSIVE_GAP_THRESHOLD
                dmg = 0
                if check["success"] and not shrugged:
                    dmg = self._damage(self.state.get("hp_max", 100), check["margin"], 0, check["breakthrough"], massive)
                    if action == "defend":
                        dmg = max(1, round(dmg * DEFEND_DAMAGE_REDUCTION))
                    self.state["hp"] = max(floor, int(self.state.get("hp", 100)) - dmg)
                combat["log"].append({"round": combat["round"], "actor": "enemy", "action": "attack",
                                       "name": enemy["name"], "damage": dmg, "extra_swing": swing_index > 0,
                                       "massive": massive, "shrugged": shrugged and check["success"], **check})
                if self.state.get("hp", 1) <= floor:
                    break

        for d in combat.get("enemy_debuffs", []):
            d["rounds_left"] = int(d.get("rounds_left", 1)) - 1
        combat["enemy_debuffs"] = [d for d in combat.get("enemy_debuffs", []) if d.get("rounds_left", 0) > 0]

        combat["round"] += 1
        self.autosave()

        if self.state.get("hp", 1) <= floor:
            return self.end_combat("defeat" if not combat.get("non_lethal") else "yielded")

        return {"combat": self.state["combat"], "hp": self.state.get("hp"), "hp_max": self.state.get("hp_max"),
                "resource": self.state.get("resource"), "resource_max": self.state.get("resource_max"),
                "log_tail": combat["log"][-3:], "player_died": False}

    def end_combat(self, outcome):
        combat = self.state.get("combat") or {}
        combat["active"] = False
        combat["outcome"] = outcome
        self.autosave()
        result = {"combat": combat, "hp": self.state.get("hp"), "hp_max": self.state.get("hp_max"),
                  "resource": self.state.get("resource"), "resource_max": self.state.get("resource_max"),
                  "log_tail": combat.get("log", [])[-5:], "player_died": outcome == "defeat"}
        if outcome == "defeat" and self.state.get("hp", 1) <= 0:
            self.state["alive"] = False
        return result

    # ---------- relaying the results (the one paid call) ----------
    def narrate_combat(self):
        """Turn everything since the last narration into prose + a normal
        state_patch (loot, injuries, quest/XP consequences) — one AI call
        covering the whole exchange, not one per round."""
        combat = self.state.get("combat") or {}
        log = combat.get("log", [])
        start = combat.get("narrated_through", 0)
        pending = log[start:]
        if not pending:
            return {"narrative": "", "story": self._flush_story()}
        mercy_shown = bool(combat.get("non_lethal") or combat.get("spare_enemy"))
        payload = {
            "task": "narrate_combat", "state": self.trimmed_state_for_ai(), "combat_outcome": combat.get("outcome"),
            "mercy_shown": mercy_shown, "mechanical_log": pending,
            "schema": {"narrative": "2-6 sentences turning the mechanical log into a real combat scene — do not re-roll or contradict any result",
                       "state_patch": "loot, injuries, XP, quest/codex/companion consequences of this fight",
                       "events": "system notifications", "timeline_event": "major event or empty",
                       "suggested_actions": ["3 concise next actions"]}}
        rules = self.gm_rules() + (
            "\nYou are narrating a fight that has ALREADY been mechanically resolved by the application. "
            "Every roll, hit, miss and HP change in mechanical_log already happened — narrate them faithfully, "
            "do not add extra unlisted hits or change any outcome. This is the same MAIN GM role as any other turn."
        )
        if mercy_shown and combat.get("outcome") in ("victory", "yielded"):
            rules += (
                " mercy_shown is true: narrate the defeated enemy's ending as knocked unconscious, restrained, "
                "or forced to yield — never killed — regardless of how much damage the mechanical log shows. "
                "If combat_outcome is 'yielded', the PLAYER is the one who was brought to the floor and conceded "
                "the bout, not defeated at risk of real harm — narrate it as the player yielding a spar/test, "
                "not a life-threatening loss."
            )
        data = self.ai.request(rules, payload, max_output_tokens=900)
        combat["narrated_through"] = len(log)
        if not combat.get("active"):
            self.state["combat"] = {}
        result = self.apply_resolution(data, is_opening=False, pending_action=f"[combat] {combat.get('outcome') or 'ongoing'}")
        return result
