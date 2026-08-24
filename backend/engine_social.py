"""Core game engine: ported from the original Tkinter App class' business
logic (character creation, assess/roll/resolve turn loop, time skips, chat,
world ticks, memory management, save/load) with all Tkinter UI code removed.
Returns plain dicts so a Flask layer can serialize them straight to JSON."""
import copy, json, random, re, secrets, threading
from datetime import datetime
from pathlib import Path

from worlds import WORLD_DATA, WORLD_EXPANSIONS, DIFFICULTIES, BASE_STATE, DEFAULT_MODEL, SECONDARY_MODEL, APP_VERSION, expansion_for, abilities_for, stat_style_for, primary_stats_for, gear_style_for, timeline_for, playable_characters_for, uses_xp_for, power_tier_reference
from ai_client import AI
from lore import format_lore_context
from portrait_generator import portrait_view
from state_guard import apply_guarded_patch, migrate_state
from continuity import update_continuity
from util import merge, clamp, safe_filename, SAVE_DIR, SETTINGS_PATH, scene_category, scene_image_url, ai_text
from systems import (progression_preset_for, normalize_tuning, normalize_quest_state_machine,
                     update_chapter_memory, tick_world_clocks)


DEFAULT_SETTINGS = {
    "provider": "local",
    "local_base_url": "http://localhost:1234/v1",
    "local_token": "",
    "api_key": "",
    "model": "",
    "secondary_model": "",
    "narration": "Concise",
    "autosave": True,
    "sound_enabled": True,
    "music_enabled": True,
    "music_volume": 0.35,
    "animations_enabled": True,
    "portrait_generation_enabled": True,
    "image_model": "gpt-image-2",
    "local_image_model": "",
    "portrait_quality": "low",
    "developer_mode": False,
}


WORLD_STARTER_GEAR = {
    "One Piece": "Travel-worn weapon and island supplies",
    "Hunter x Hunter": "Practical travel gear and training wraps",
    "Naruto": "Kunai pouch, shuriken and field supplies",
    "Solo Max-Level Newbie": "Beginner weapon and emergency potion",
    "Overgeared": "Beginner equipment set and trade tools",
    "Reincarnated as a Slime": "Species-appropriate natural weapon or focus",
    "Custom World": "Setting-appropriate weapon and travel kit",
}

WORLD_STARTER_SKILL = {
    "One Piece": "Foundation Combat Style", "Hunter x Hunter": "Conditioned Fundamentals",
    "Naruto": "Academy Fundamentals", "Solo Max-Level Newbie": "System Adaptation",
    "Overgeared": "Class Fundamentals", "Reincarnated as a Slime": "Intrinsic Species Trait",
    "Custom World": "Background Expertise",
}

POOL_STATS = {
    "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
    "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
    "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
    "Solo Max-Level Newbie": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Overgeared": (("Constitution", "Strength"), ("Intelligence", "Wisdom")),
    "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
    "Custom World": (("Constitution", "Strength"), ("Wisdom", "Intelligence")),
}

ABILITY_ASPECTS = {
    "fire": "Ember", "flame": "Ember", "heat": "Ember", "water": "Tide",
    "wind": "Gale", "air": "Gale", "lightning": "Storm", "electric": "Storm",
    "earth": "Stone", "ice": "Frost", "shadow": "Shadow", "dark": "Shadow",
    "light": "Radiance", "heal": "Renewal", "medical": "Renewal", "sense": "Echo",
    "sensor": "Echo", "speed": "Flash", "strong": "Titan", "strength": "Titan",
}

WORLD_ABILITY_FORMS = {
    "Naruto": [
        ("{aspect} Thread Technique", "a personal chakra transformation discovered during uneven early training",
         "forms fine {aspect_lower}-natured chakra threads for precise attacks, traps, sensing, or utility",
         "complex shapes quickly exhaust chakra and collapse when concentration breaks",
         "improve chakra control, learn the matching nature transformation, and develop larger stable patterns"),
        ("{aspect} Pulse", "an unusual chakra response first triggered during a formative moment",
         "releases a short pulse of {aspect_lower}-aligned chakra whose exact use adapts to the user's intent",
         "has short range and becomes unreliable when emotionally or physically exhausted",
         "practice controlled pulses, study sealing principles, and learn to sustain the effect"),
    ],
    "One Piece": [
        ("{aspect} Imprint Style", "an improvised island fighting art shaped by the character's environment",
         "imprints {aspect_lower}-themed force or motion into strikes, tools, and movement without ignoring physical limits",
         "requires preparation and stamina; stronger effects expose the user to retaliation",
         "condition the body, refine timing, and eventually combine the style with Haki if it is learned"),
        ("{aspect} Instinct", "a rare natural sensitivity that has not yet matured into formal Haki",
         "notices subtle {aspect_lower}-like patterns in danger, movement, and intent a moment earlier than normal",
         "provides impressions rather than certainty and fails amid overwhelming chaos",
         "survive demanding encounters, train awareness, and seek instruction in Observation Haki"),
    ],
    "Hunter x Hunter": [
        ("{aspect} Resonance", "a dormant Nen inclination expressed before the character understands aura",
         "causes aura to resonate with {aspect_lower}-themed conditions and hints at a future personal Hatsu",
         "remains inconsistent until the character properly opens and controls their aura nodes",
         "learn Ten, Ren, Zetsu and Hatsu, then define restrictions that strengthen the effect"),
        ("{aspect} Tell", "an exceptional learned instinct that may later become a Nen technique",
         "reads small bodily and environmental cues through a {aspect_lower}-themed mental association",
         "can be deceived and becomes noisy under stress or unfamiliar conditions",
         "test the instinct, study opponents, and later reinforce it with a suitable Nen category"),
    ],
    "Solo Max-Level Newbie": [
        ("Adaptive Skill: {aspect} Script", "a background-derived trait recognized when the System evaluates the player",
         "builds proficiency when the player repeats successful {aspect_lower}-aligned solutions",
         "starts at low rank and loses efficiency when the same trick is forced into unsuitable situations",
         "meet hidden conditions, diversify applications, and earn System achievements"),
    ],
    "Overgeared": [
        ("Rare Skill: {aspect} Craft", "a personal knack translated into a Satisfy-compatible skill",
         "adds {aspect_lower}-themed properties to appropriate crafted items or class techniques",
         "success depends on materials, production skill, design quality, and class compatibility",
         "raise production mastery, acquire better materials, and complete a related class quest"),
    ],
    "Reincarnated as a Slime": [
        ("Extra Skill: {aspect} Weave", "a desire and prior-life inclination crystallized into a world-valid skill",
         "shapes magicules into controlled {aspect_lower}-themed effects suited to the user's species",
         "output is limited by magicule capacity, analysis, resistances, and control",
         "increase magicule capacity, analyze related phenomena, and combine compatible skills"),
    ],
    "Custom World": [
        ("{aspect} Gift", "a setting-consistent talent produced from the player's requested parameters",
         "creates a flexible {aspect_lower}-themed effect within the established rules of the custom world",
         "begins narrow in scope and cannot bypass costs, counters, or prerequisites established by the setting",
         "practice its core use, discover its source, and earn broader applications through play"),
    ],
}

class SocialMixin:
    def ask_advisor(self, question, fourth_wall=False):
        """A Pax Historia-style Advisor: an out-of-character, meta-aware
        guide the player can consult any time for power-level assessments,
        world-state summaries, and strategic advice — NOT an in-fiction NPC,
        so it isn't bound by 'only knows what they'd plausibly know', and it
        never touches game state (no dice, no state_patch, no turn cost)."""
        with self.lock:
            self.state.setdefault("advisor_thread", []).append({"role": "player", "text": question, "turn": self.state.get("turn", 0)})
        if not self.ai_ready():
            entry = {"role": "advisor", "summary": "The Advisor is unavailable — configure a model in AI & Portrait Setup first.", "points": [], "follow_ups": [], "turn": self.state.get("turn", 0)}
            with self.lock:
                self.state["advisor_thread"].append(entry)
            return {"entry": entry, "state": self.public_state()}
        # A one-word "thanks" or a quick "how strong am I?" doesn't deserve
        # the same 4-8 point structured briefing as a real strategy question
        # — mirrors Pax Historia's own Advisor, which detects a short player
        # message and short-circuits to a one-sentence reply instead of its
        # full analysis format. Word count, not character count: this is a
        # conversational question, not a chat acknowledgment, so a 10-char
        # cutoff would almost never fire on an actual short question.
        concise = len(str(question).split()) <= 6
        wants_chart = bool(re.search(r"\b(graph|chart|plot|visuali[sz]e|bar\s*chart)\b", str(question), re.I))
        payload = {
            "task": "advisor_question", "question": question, "state": self.trimmed_state_for_ai(),
            "advisor_mode": "fourth_wall" if fourth_wall else "strategic", "next_canon_event": self.canon_countdown(),
            "canon_divergences": self.state.get("canon_divergences") or [],
            "thread_history": self.state.get("advisor_thread", [])[-16:],
            "schema": {
                "summary": ("ONE direct sentence answering the question — nothing more" if concise else
                            "2-4 direct sentences answering the question with a bottom line and important context"),
                "points": ([] if concise else
                           ["4-8 substantive supporting points with evidence, comparison, timing, odds, tradeoffs or concrete next steps"]),
                "follow_ups": ([] if concise else
                               ["2-3 short natural follow-up questions the player might want to ask next, phrased as the PLAYER would ask them"]),
                "chart": ("null unless the player explicitly asked for a graph/chart/visual comparison, or the answer is fundamentally "
                          "a numeric comparison across 3+ things a chart would communicate faster than prose — in which case: "
                          '{"title": "short chart title", "unit": "what the numbers mean, e.g. \'DBZ Power Level\'", '
                          '"items": [{"label": "name", "value": number}, ...2-8 entries, highest first]}'),
            },
        }
        rules = f"""You are "The Advisor" for {self.state.get('world','the world')} — a Dungeon Master the player can lean over and ask a question any time play pauses. You are NOT an in-fiction character and not bound by "NPCs only know what they'd plausibly know" — you know everything tracked plus this world's full canon.
Voice: talk TO the player, like a DM answering a question at the table — direct, plain, second person ("you're", "they've"), a real opinion when asked for one. Not a report, not a wiki article. This applies to every kind of question, not just rules questions — a strategy or world-state answer should still sound like a person talking, just with more to say.
You may freely:
- Assess relative power levels of the player, companions, rivals, factions and known threats, using terms appropriate to this world (bounty/Haki tier, Nen category/rank, jutsu/village rank, class/level, etc.) by default.
- If the player asks for a specific comparison framework instead — a numeric scale, tiers, percentages, or even a well-known scale borrowed from another series (e.g. "give me this in DBZ power levels") — use exactly the framing they asked for as a communication device to convey relative strength, even when it isn't native to this world. It's a translation aid, not a claim that this world works that way.
- When you need your OWN internal sense of "how strong is strong" — placing the player, a companion, or a threat on a scale, deciding whether a fight is winnable, judging if a request for a graph makes sense numerically — anchor to this reference ladder instead of improvising a different scale each time:
{power_tier_reference()}
  This ladder is scaffolding for your own consistency, never shown to the player unless they specifically ask for a numbered/tiered framing. Once you've placed a named character at a tier across this conversation, stay consistent with that placement rather than re-ranking them differently next time without a stated in-world reason (a real power-up, new information, etc.).
- Summarize the current state of the world: active threats, opportunities, unresolved plot threads, faction tensions, quest status.
- When asked why an NPC feels a certain way or why a faction's standing is what it is, answer from that NPC's npc_memories[name].chain or the faction's faction_chain[name] entries in state if present — they're the real recorded reasons, not something to re-guess from scratch. Only fall back to reasoning from campaign_canon/narrative history when no chain entry exists yet (an older campaign predating this feature, or a relationship that's never had a real turning point).
- Give honest strategic advice, including risks and trade-offs. Never decide for the player — lay out the options.
- Every world-state or planning answer must reference the supplied next_canon_event countdown and explain whether current plans can fit before it.
- ASKED ABOUT SOMETHING NOT IN THE TRACKED STATE (an off-screen character, faction, or event the player hasn't personally touched): don't deflect to "I don't know" or "that's not tracked." Answer it — reason from this world's canon AT THE CURRENT POINT IN THE TIMELINE (the tracked world_time/canon day, never spoiling events still ahead of it), the same way a DM who knows the source material would. First check canon_divergences: if a recorded divergence changed that person/place/event, the divergence is the truth and overrides stock canon — say so plainly ("in this campaign, X happened instead, because..."). BAD: "That's not something I have tracked information on." GOOD: "He's not someone you've crossed paths with, but canonically he'd still be running the western trade routes at this point in the story — reasoning from that, here's what he's probably doing..." Only hedge when canon genuinely never reveals the answer even in principle — and even then, give your best-reasoned read before admitting the limit, don't lead with the disclaimer.
- When the question is really a rules/mechanics clarifying question (how something works, what's allowed, what would happen if...), walk through it directly with an example if that helps — never a dry analytical report.
- When the player explicitly asks for a graph/chart/visual comparison, or the honest best answer to their question is fundamentally "here's how N things stack up numerically," fill in the chart field per the schema instead of (or alongside) explaining it in prose — don't just describe numbers in a sentence when they asked to see them.
{"FOURTH-WALL MODE IS ON. You may additionally expose and analyze the simulation's d100 math, generated difficulty range, stat/title bonuses, queue/time-budget behavior, canon-stop boundaries, AI uncertainty, save/rewind behavior, and clever ways to exploit those rules without falsifying state or changing it. Clearly distinguish engine facts from speculative model behavior." if fourth_wall else "FOURTH-WALL MODE IS OFF. Stay focused on story-world strategy and tracked facts; do not discuss software or hidden engine implementation."}
{"THE PLAYER'S MESSAGE WAS SHORT/LOW-EFFORT — MIRROR THAT. Answer in exactly one direct sentence. Leave points and follow_ups empty. Do not pad a quick question into a full structured briefing, even if you could say more — the only exception is if the question is truly impossible to answer in one sentence, in which case answer as briefly as the question actually allows." if concise else "Give a real briefing: enough to support a decision, organized and concrete, but still sounds like someone talking to you, not a form being filled out."}
{"THE PLAYER'S WORDING SUGGESTS THEY WANT A VISUAL (graph/chart/plot) — populate the chart field; don't just describe the numbers in prose instead." if wants_chart else ""}
You never alter game state; this is a conversation only. Return ONLY valid JSON, no markdown fences."""
        data = self.ai.request(rules, payload, max_output_tokens=200 if concise else 1000)
        entry = {
            "role": "advisor",
            "summary": (data.get("summary") or "").strip() or "...",
            "points": [ai_text(p) for p in (data.get("points") or []) if ai_text(p)][:8],
            "follow_ups": [ai_text(q) for q in (data.get("follow_ups") or []) if ai_text(q)][:3],
            "chart": self._sanitize_advisor_chart(data.get("chart")),
            "fourth_wall": bool(fourth_wall), "canon_countdown": self.canon_countdown(),
            "turn": self.state.get("turn", 0),
        }
        with self.lock:
            self.state.setdefault("advisor_thread", []).append(entry)
            self.autosave()
        return {"entry": entry, "state": self.public_state()}

    @staticmethod
    def _sanitize_advisor_chart(raw):
        """The model sometimes returns chart items with a non-numeric value,
        a missing label, or more entries than the schema asked for — none of
        that should be able to break rendering, so coerce or drop rather
        than trusting the shape."""
        if not isinstance(raw, dict):
            return None
        items = []
        for item in (raw.get("items") or [])[:8]:
            if not isinstance(item, dict):
                continue
            label = ai_text(item.get("label") or item.get("name") or "")
            value = item.get("value")
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if not label:
                continue
            items.append({"label": label, "value": value})
        if not items:
            return None
        return {
            "title": ai_text(raw.get("title") or "") or "Comparison",
            "unit": ai_text(raw.get("unit") or ""),
            "items": items,
        }

    def ensure_contact(self, name, kind="person", details=None):
        if not name:
            return
        c = self.state.setdefault("contacts", {}).setdefault(name, {
            "name": name, "kind": kind, "status": "Known", "relationship": 0, "last_known_location": "Unknown",
            "notes": [], "can_contact": True, "first_met_turn": self.state.get("turn", 0)
        })
        if details and isinstance(details, dict):
            c.update(details)
        self.state.setdefault("chat_threads", {}).setdefault(name, [])

    def add_chat_message(self, thread, sender, text, direction="incoming", metadata=None):
        self.ensure_contact(thread, "group" if thread in self.state.get("group_chats", {}) else "person")
        msg = {"time": self.state.get("world_time", "Unknown"), "turn": self.state.get("turn", 0),
               "sender": sender, "text": text, "direction": direction, "metadata": metadata or {}}
        self.state.setdefault("chat_threads", {}).setdefault(thread, []).append(msg)
        if direction == "incoming":
            self.state.setdefault("unread_chats", []).append({"thread": thread, "turn": self.state.get("turn", 0)})
        return msg

    def resolve_side_chat(self, thread, message):
        with self.lock:
            self.add_chat_message(thread, self.state.get("name", "You"), message, "outgoing")
        if not self.ai_ready():
            return {"state": self.public_state(), "story": self._flush_story()}
        contact = self.state.get("contacts", {}).get(thread, {})
        # Same effort-matching as the Advisor's concise mode: a one-line
        # text doesn't need the same output budget as a real negotiation
        # attempt, and asking for less also reinforces the length-matching
        # instruction below rather than leaving the model room to pad anyway.
        concise = len(str(message).split()) <= 6
        payload = {
            "task": "side_chat_reply", "role": "Narrator + NPC dialogue", "thread": thread, "player_message": message,
            "state": self.trimmed_state_for_ai(), "thread_history": self.state.get("chat_threads", {}).get(thread, [])[-20:],
            "contact": contact, "reputation": self.state.get("reputation", {}), "affiliations": self.state.get("affiliations", []),
            "requirements": [
                "Respond naturally as the contacted NPC/group if they are able and willing to respond — this is real-time back-and-forth, not a narrated summary of the conversation.",
                "They may ignore, delay, refuse, lie, misunderstand, ask questions, or end the conversation.",
                "Base tone, willingness to help, and honesty on the player's actual reputation/standing with this specific person or group and any relevant affiliation/rank — a hostile or unfamiliar faction should be curt, guarded, or refuse outright; a trusted contact or fellow member should be warmer and more forthcoming. Never treat the player as automatically trusted or important.",
                "Text the player wrote in [brackets] is a physical action attempted during the conversation (a gesture, handing something over, drawing a weapon, leaving), not something said aloud — react to it as an action with real in-fiction weight, not as dialogue.",
                "Use lore-appropriate communication methods for this contact — an individual might text/message/scry/etc., but a large faction/polity typically replies through a representative, herald, official channel, or delay appropriate to their scale, not as if the whole organization is one person instantly texting back.",
                "Do not pause or replace the main adventure scene.",
                "Before responding, check campaign_canon (recent turn history) and this contact's npc_memories entry for anything the player and this contact have already done, discussed, or resolved together — including in the main scene, not just prior chat messages. Never have them ask about, re-propose, or act surprised by something already settled; reference it as already known instead.",
                "Any meaningful promise, information, relationship change, quest lead, or arrangement must be represented in state_patch.",
                "If this conversation creates a promise, deadline, grudge, standing order, or new agenda item for the contacted person or group, record it in state_patch.scheduled_events (with due_canon_day) and/or update their entry in npc_clocks/faction_clocks — a commitment made here must be able to resurface naturally in a future world update, the same as one made in the main scene.",
                "Keep the reply's length roughly proportional to the player's message — a short line deserves a short reply, not a paragraph; match their register and effort rather than always writing at maximum length."
            ],
            "schema": {"reply": "string or empty if no immediate reply", "sender": "speaker",
                       "state_patch": "contacts, npc_memories, relationships, quests, scheduled_events, npc_clocks, faction_clocks or other side-chat consequences",
                       "events": "system notifications if needed"}
        }
        data = self.ai.request(self.core_rules(), payload, max_output_tokens=150 if concise else 500)
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="side_chat")
            reply = data.get("reply", "").strip()
            if reply:
                sender = data.get("sender") or thread
                self.add_chat_message(thread, sender, reply, "incoming")
            notifications = self.notify(before, self.state, data.get("events", []))
            update_continuity(before, self.state, f"Message to {thread}: {message}", data.get("reply", ""))
            self.autosave()
        return {"reply": data.get("reply", ""), "notifications": notifications, "state": self.public_state(), "story": self._flush_story()}

    def maybe_generate_incoming_chat(self):
        if self.busy or not self.ai_bg_ready() or not self.state.get("contacts"):
            return None
        if self.state.get("turn", 0) % 2 != 0:
            return None
        payload = {
            "task": "incoming_chat_check", "role": "World/NPC Simulator", "state": self.trimmed_state_for_ai(),
            "requirements": [
                "Determine whether any known contact or group would plausibly message the player right now.",
                "Do not force a message. If nobody has a reason, return send=false.",
                "Base motivation on current events, relationship, quests, prior promises, faction activity, danger, rumors, or the NPC's own goals.",
                "The sender may only know information they could realistically know.",
                "Keep messages natural and in-character.",
                "Major recurring canon/world characters should be favored when they have a strong reason to contact the player.",
                "Current companions who are not physically present this turn are especially plausible senders — they have an ongoing stake in the player's life and should check in, share news, or follow up on their own initiative, not only when the player messages first.",
                "Before proposing any plan, activity, question, or piece of news, check campaign_canon (recent turn history) and this contact's npc_memories entry for whether it has already happened, been discussed, or been resolved with the player. Never pitch something already done together as a new idea, ask about something already answered, or act surprised by something the player already told them — if it's already settled, either don't send a message about it at all, or reference it as something already known (a follow-up, a thank-you, a next step) rather than raising it as if for the first time."
            ],
            "schema": {"send": "boolean", "thread": "contact/group name", "sender": "speaker name",
                       "message": "short natural chat message", "contact_patch": "optional contact/group metadata updates"}
        }
        rules = self.core_rules(extra="You are checking for an unsolicited communication event, not advancing the main scene.\n"
                                      "Messages are asynchronous side communications. Preserve lore, technology, communication methods, distance, and world rules.\n"
                                      "If the world has no modern phones, interpret 'chat' as the nearest lore-appropriate medium: Den Den Mushi, messenger, letter, radio, courier, system message, guild chat, etc.")
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=350)
        except Exception as e:
            self.log("Background chat check failed: " + str(e))
            return None
        if not data.get("send"):
            return None
        with self.lock:
            thread = data.get("thread") or data.get("sender")
            sender = data.get("sender") or thread
            self.ensure_contact(thread, "group" if data.get("contact_patch", {}).get("kind") == "group" else "person", data.get("contact_patch") or {})
            self.add_chat_message(thread, sender, data.get("message", ""), "incoming")
            self.append(f"[MESSAGE — {thread}]\n{sender}: {data.get('message', '')}", "system")
            self.log(f"Incoming message from {sender} in {thread}")
            self.autosave()
        return {"thread": thread, "sender": sender, "message": data.get("message", "")}

    def create_world_event_if_due(self):
        current_day = int(self.state.get("canon_day", 0) or 0)
        last_tick_day = self.state.get("last_protagonist_tick_day")
        if last_tick_day is None:
            # First time this runs for a campaign — establish the baseline
            # without firing immediately (there's no "since last time" yet).
            self.state["last_protagonist_tick_day"] = current_day
            last_tick_day = current_day
        due_by_day = (current_day - int(last_tick_day)) >= 30
        due_by_turn = bool(self.state.get("turn", 0) and self.state["turn"] % 4 == 0)
        if not ((due_by_day or due_by_turn) and self.ai_bg_ready() and not self.busy):
            return None
        world = self.state.get("world", "Custom World")
        canon_cast = playable_characters_for(world)
        protagonist = canon_cast[0].get("name") if canon_cast else None
        payload = {"task": "background_world_tick", "state": self.trimmed_state_for_ai(), "protagonist": protagonist or "",
                   "requirements": [
                       "Advance off-screen NPC/faction activity by a modest amount. Do not teleport anyone. Do not force the player into a scene.",
                       (f"This world's canon protagonist is {protagonist}. Advance their own canon-consistent arc by roughly a month's worth of activity in the background — training, missions, relationships, canon plot beats — and record it via npc_memories or other justified state_patch fields, whether or not the player currently knows any of it. Their story keeps moving forward on its own timeline even when the player never crosses paths with them."
                        if protagonist else "This world has no single canon protagonist to track — just advance the wider world as usual."),
                       "Only return a player-visible heard_event when this tick's changes would actually reach or affect the player or a portion of the world connected to them — never for the protagonist's own routine, unconnected progress. Most ticks should leave heard_event empty."
                   ],
                   "schema": {"state_patch": "world_events, npc_memories, factions, canon_divergences or other justified world-state changes", "heard_event": "brief rumor/news/observation or empty"}}
        rules = self.core_rules(extra="This is a background simulation tick. Preserve geography, travel time, NPC knowledge and causality. Do not resolve a player action.")
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=450)
        except Exception as e:
            self.log("World tick failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="world_tick")
            self.state["last_protagonist_tick_day"] = current_day
            heard = data.get("heard_event", "").strip()
            if heard:
                self.append("[WORLD UPDATE]\n" + heard, "system")
                self.log("World update: " + heard)
            update_continuity(before, self.state, "Background world tick", heard)
            self.autosave()
        return {"heard_event": data.get("heard_event", "")}

    # allow_time=False (apply_guarded_patch) only blocks time/calendar
    # fields — it was never meant to be a general "background-tick-safe"
    # filter, so a reentry recap needs its own explicit whitelist to
    # actually guarantee it can't touch the player's own stats, inventory,
    # currency, or location, matching what the prompt asks for with a real
    # mechanical backstop instead of trusting the model to comply.
    REENTRY_RECAP_ALLOWED_PATCH_FIELDS = {"npc_memories", "factions", "canon_divergences", "npc_relationships", "faction_clocks", "npc_clocks"}

    def generate_reentry_recap(self):
        """A short narrated "since you've been away" paragraph, triggered
        from load() detecting a real-world gap (see
        REENTRY_RECAP_THRESHOLD_HOURS) — the one place the world visibly
        keeps moving purely because time passed for the PLAYER, not because
        they took any action. Deliberately narrative-only: no canon_day/
        world_time movement (ordinary player absence can never advance
        those, same rule as an ordinary turn), and the allowed state_patch
        is restricted the same way the background world tick's already is,
        so this can record real off-screen developments (an NPC's goal
        advancing, a faction's fortunes shifting) without ever touching the
        player's own stats, inventory, currency, or location."""
        hours = self._pending_reentry_hours
        self._pending_reentry_hours = None
        if not hours or not self.ai_bg_ready() or self.busy:
            return None
        payload = {
            "task": "reentry_recap", "hours_away": hours, "state": self.trimmed_state_for_ai(),
            "recent_background_feed": (self.state.get("background_world_feed") or [])[-10:],
            "requirements": [
                f"The player was away from the app for about {hours:.0f} hours of real time — not in-game time, which has not moved (ordinary absence never advances world_time/canon_day, exactly like an ordinary turn never does).",
                "Write ONE short narrated paragraph (3-6 sentences) of what plausibly stirred elsewhere while the player wasn't looking, grounded in recent_background_feed and any tracked npc_clocks/faction_clocks/npc_relationships — build on threads already in motion rather than inventing disconnected new ones.",
                "This is atmosphere reaching the player on return (a messenger, a notice, something a companion mentions), not something that happened TO the player — never move the player's own location, stats, currency, inventory, or HP, and never advance canon_day/world_time/calendar.",
                "Keep it proportional to the gap — a few hours away is a quiet aside, not a war concluding. Modest off-screen movement (npc_memories, factions, canon_divergences) may still be recorded via state_patch the same way the regular background world tick can, but nothing time- or player-state-related.",
                "If genuinely nothing worth narrating has moved, return an empty recap rather than manufacturing filler.",
            ],
            "schema": {"recap": "the paragraph, or empty", "state_patch": "npc_memories, factions, canon_divergences or other justified non-time, non-player-state changes only"},
        }
        rules = self.core_rules(extra="This is a reentry recap, not a scene and not a time skip. Do not resolve a player action. Do not advance time.")
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=350)
        except Exception as e:
            self.log("Reentry recap failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            # allow_time=False on its own only blocks time/calendar fields,
            # not general player-state ones — the requirements above ask
            # the model nicely not to touch hp/currency/location, but
            # nothing enforced that until this whitelist. A real turn earns
            # the right to touch player state; a background recap the
            # player didn't act to trigger does not.
            raw_patch = data.get("state_patch", {})
            safe_patch = {k: v for k, v in raw_patch.items() if k in self.REENTRY_RECAP_ALLOWED_PATCH_FIELDS} if isinstance(raw_patch, dict) else {}
            apply_guarded_patch(self.state, safe_patch, allow_time=False, source="reentry_recap")
            recap = str(data.get("recap", "")).strip()
            if recap:
                self.append("[WHILE YOU WERE AWAY]\n" + recap, "narrative")
                self.log("Reentry recap generated.")
            update_continuity(before, self.state, "Reentry recap", recap)
            self.autosave()
        return {"recap": recap, "state": self.public_state(), "story": self._flush_story()}

    def run_memory_manager(self):
        if not self.ai_bg_ready() or self.busy:
            return None
        payload = {"task": "memory_manager", "role": "Memory Manager", "state": self.trimmed_state_for_ai(),
                   "requirements": "Compress/update recurring NPC memories, relationship facts, promises, debts, suspicions, discovered facts, and last-known locations. Preserve uncertainty and delete nothing important. Do not narrate a scene.",
                   "schema": {"state_patch": "npc_memories, contacts, chat_threads metadata, relationships, codex, location_details, ability_progress or other memory-oriented changes only", "memory_note": "brief maintenance note or empty"}}
        rules = self.core_rules(extra="You are the MEMORY MANAGER. Be conservative. Never invent player actions, secret knowledge, or relationship changes unsupported by the state.")
        try:
            data = self.ai_bg.request(rules, payload, max_output_tokens=450)
        except Exception as e:
            self.log("Memory manager failed: " + str(e))
            return None
        with self.lock:
            before = copy.deepcopy(self.state)
            apply_guarded_patch(self.state, data.get("state_patch", {}), allow_time=False, source="memory_manager")
            note = data.get("memory_note", "").strip()
            if note:
                self.log("Memory: " + note)
            update_continuity(before, self.state, "Continuity audit", note)
            self.autosave()
        return {"memory_note": data.get("memory_note", "")}

    def sync_contacts_from_state(self):
        with self.lock:
            for name, mem in self.state.get("npc_memories", {}).items():
                if not isinstance(mem, dict):
                    continue
                significance = mem.get("importance", mem.get("significance", ""))
                recurring = mem.get("recurring", False) or significance in ("major", "important", "high")
                can_contact = mem.get("can_contact", False) or mem.get("contact_method")
                if recurring or can_contact:
                    self.ensure_contact(name, "person", {
                        "last_known_location": mem.get("last_known_location", "Unknown"),
                        "can_contact": bool(can_contact),
                        "contact_method": mem.get("contact_method", "Lore-appropriate"),
                        "notes": mem.get("notes", [])
                    })
            self.autosave()
