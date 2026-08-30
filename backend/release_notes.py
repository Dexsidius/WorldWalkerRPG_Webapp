"""Player-facing release notes shown once per browser/account and version."""

RELEASE_NOTES = {
    "3.44.1": {
        "title": "Reliable Economy and Poneglyph Chronicle",
        "summary": "Money changes are now auditable and exact, recurring expenses become payable obligations instead of negative balances, and One Piece turns arrive on the approved anime-style Poneglyph stone.",
        "highlights": [
            {"title": "Exact world currencies", "example": "A 0.5 Gold Coin purchase in the Slime world now deducts the correct Silver/Copper equivalent instead of becoming free."},
            {"title": "Money history", "example": "Purchases, income, expenses, and payments appear in a compact Bag ledger with the reason for every change."},
            {"title": "Payable obligations", "example": "Rent or wages that exceed available cash leave the balance at zero and create an outstanding obligation the player can pay later."},
            {"title": "Secondary-currency shops", "example": "Arena tokens, guild points, and other distinct currencies can price and purchase their own items without spending the primary balance."},
            {"title": "Reusable purchases stay useful", "example": "Bought equipment preserves its effect, rating, category, and restrictions when it enters the Bag."},
            {"title": "Narrative-only economies protected", "example": "Bleach and JJK cannot accidentally acquire a permanent money meter or price-gated offers from an AI patch."},
            {"title": "Wealth separated from power", "example": "Starting as immeasurably strong no longer silently creates extra money unless the background also establishes wealth."},
            {"title": "One Piece Poneglyph Chronicle", "example": "Each One Piece turn now sinks into place as a bright cel-shaded blue stone with readable carved-style lettering."},
        ],
    },
    "3.44.0": {
        "title": "Causal GM and World-Native Character Sheets",
        "summary": "Actions resolve more directly, AI jobs use smaller focused prompts, oversized campaigns recover automatically, and every world receives its approved Attributes design plus bundled canon portrait art.",
        "highlights": [
            {"title": "Causal outcomes", "example": "A successful private action can simply work; setbacks now require a concrete cause, believable awareness, a motive, and proportional scale."},
            {"title": "No manufactured drama", "example": "Solved problems stay solved, quiet victories are valid, and canon no longer bends an original campaign back toward the source plot."},
            {"title": "Focused AI jobs", "example": "Assessment, time planning, combat summaries, and continuity repair receive only the rules and context needed for their specific task."},
            {"title": "Long-campaign request recovery", "example": "Cloud requests are compacted to about 80k tokens and automatically retry near 60k if the provider rejects an oversized request."},
            {"title": "World-specific Attributes", "example": "Naruto uses a shinobi scroll, One Piece a bounty record, Overgeared a Satisfy window, Bleach a monochrome dossier, and every other world has its approved native treatment."},
            {"title": "Bundled canon portraits", "example": "Approved canon starts and supported transformations load from local art instead of spending an image-generation request."},
            {"title": "Cleaner Naruto pointers", "example": "The Naruto kunai cursor and spinning shuriken loading indicator now better match their source-world silhouettes."},
            {"title": "Full regression coverage", "example": "The patch passes 785 automated checks covering campaigns, worlds, combat, saves, mobile behavior, prompts, and UI contracts."},
        ],
    },
    "3.43.0": {
        "title": "Long Campaign Stability",
        "summary": "Long-running campaigns now repair stale bookkeeping before Advance, preserve complete standing plans, recover partial AI replies, and store history far more efficiently.",
        "highlights": [
            {"title": "Pre-Advance campaign health check", "example": "Before a turn begins, malformed deep state is repaired locally so an old save cannot crash before rollback protection starts."},
            {"title": "Stale goals retire cleanly", "example": "A training goal from dozens of turns ago is archived when its plan is no longer active instead of contaminating the current scene."},
            {"title": "Quests and scenes reconcile", "example": "Completed quests move to the archive, duplicates disappear, and the live scene follows the character's actual location."},
            {"title": "Stale combat closes itself", "example": "Combat cannot remain active with a defeated opponent, missing enemy, or incapacitated player and block every later action."},
            {"title": "Much smaller save snapshots", "example": "Undo checkpoints keep current facts but no longer repeat hundreds of old events and diagnostics in every copy."},
            {"title": "Deep schema repair", "example": "Malformed NPC dossiers, combatants, quest rows, histories, and nested containers are normalized with exact diagnostic paths."},
            {"title": "Actionable error IDs", "example": "An unexpected API failure returns a short support ID while preserving the campaign and recording the failing route and data shape."},
            {"title": "Partial AI replies survive", "example": "If a model returns updates or state changes without its main narrative field, the usable result is recovered without paying for another call."},
            {"title": "Hot, warm, and cold memory", "example": "Recent turns, chapter summaries, and verified archives are separated so the GM gets relevant history without resending the full save."},
            {"title": "Standing orders have a lifecycle", "example": "A multi-action plan keeps every unfinished instruction across Moments while completed, deferred, and replaced orders are tracked separately."},
            {"title": "Readable NPC development updates", "example": "Off-screen growth now distinguishes training progress, ongoing story movement, and an NPC approaching a decision instead of calling every goal an overdue commitment."},
        ],
    },
    "3.42.1": {
        "title": "Long-Campaign Advance Recovery",
        "summary": "Advance now accepts compact companion names correctly and automatically removes misplaced response-envelope data from NPC memories.",
        "highlights": [
            {"title": "String companions no longer block Advance", "example": "Campaigns with companions stored as names such as Emi Kuroda can prepare canon context and advance normally."},
            {"title": "NPC-memory namespace repaired", "example": "Misplaced fields such as elapsed time, quests, and completed actions are removed during import/load without deleting real NPC dossiers."},
            {"title": "Future corruption blocked", "example": "Malformed AI patches are filtered at the state boundary before unrelated response fields can enter NPC memories."},
            {"title": "Existing campaigns recover on load", "example": "Loading or importing the campaign applies the repair automatically; a new character is not required."},
            {"title": "Standing plans remain intact", "example": "A queued multi-action plan continues in its original order after the campaign is repaired."},
            {"title": "Real NPC histories are preserved", "example": "Relationships, knowledge, goals, and memories belonging to named characters survive the cleanup."},
            {"title": "Compact and structured companions coexist", "example": "Older name-only companions and newer detailed companion records can safely appear in the same campaign."},
            {"title": "Reported save shape is regression-tested", "example": "Automated coverage now prepares and resolves Advance from the same companion and standing-order layout as the affected turn-311 save."},
        ],
    },
    "3.42.0": {
        "title": "Resilient Turns and Deeper Campaign Continuity",
        "summary": "Turns now recover atomically from malformed AI output while active scenarios, combat stakes, milestones, messages, generated powers, costs, and long-campaign testing receive stronger local support.",
        "highlights": [
            {"title": "Failed turns cannot half-apply", "example": "If an Advance response crashes during processing, the campaign returns to the exact clean pre-turn state and keeps a safe Retry Failed Turn option."},
            {"title": "Broader AI-response repair", "example": "Compact events, updates, chats, assessment rows, and combatants are converted into usable structures before gameplay reads them."},
            {"title": "Active scenario memory", "example": "A continuing fight or major situation carries its cause, objective, stakes, location, and latest development into later GM and Advisor context."},
            {"title": "Smarter original-power uniqueness", "example": "Renaming a momentum-storage technique no longer makes it count as a different generated power."},
            {"title": "Long-campaign stability", "example": "The bounded Chronicle and prompt budgets keep old campaigns responsive without deleting their saved history."},
            {"title": "Clear combat context", "example": "Combat shows why it began, what ends it, and what is at risk above the action controls."},
            {"title": "More grounded messages", "example": "Known contacts can warn, check on, congratulate, or follow up based on the actual event and their relationship."},
            {"title": "World-native milestones", "example": "Shikai, bounties, Haki, Nen, grades, floor clears, Satisfy classes, and evolutions receive deduplicated setting-specific records."},
            {"title": "Per-turn AI cost visibility", "example": "Diagnostics now records the model, task, token use, and estimated cost of the latest narrated turn alongside session totals."},
            {"title": "Expanded free playtest matrix", "example": "Every built-in world is automatically checked for capability, progression, NPC, scenario, malformed-response, and transaction contracts without spending AI credits."},
        ],
    },
    "3.41.1": {
        "title": "Advance and Combat Hotfix",
        "summary": "Advance now safely accepts compact or malformed combat data instead of trapping the campaign behind a string-object error.",
        "highlights": [
            {"title": "Advance no longer stalls", "example": "An AI response such as enemy: Tunnel Guard is converted into a complete combatant record before the turn continues."},
            {"title": "Nested combat recovery", "example": "Malformed status, cooldown, log, contact, and message-delivery shapes are normalized before gameplay reads them."},
            {"title": "Existing campaigns repair themselves", "example": "Loading and advancing an affected save preserves the opponent's name and repairs the combat structure automatically."},
            {"title": "Opponent identity is preserved", "example": "A compact enemy name remains Tunnel Guard instead of becoming a generic Enemy during repair."},
            {"title": "Status lists are hardened", "example": "A compact Paralyzed status becomes a usable timed status record rather than breaking combat."},
            {"title": "Stale checks are harmless", "example": "Malformed legacy difficulty rows are ignored while valid actions still resolve."},
            {"title": "Messages cannot break Advance", "example": "Old contact and message-delivery values are repaired before reactive messages are processed."},
            {"title": "All v3.41.0 features retained", "example": "Autonomous companions, NPC development, ability history, downtime, recovery tools, and narrative Satisfy classes remain enabled."},
        ],
    },
    "3.41.0": {
        "title": "A World That Keeps Moving",
        "summary": "Long skips, companions, NPCs, abilities, messages, recovery, and Satisfy classes now develop through persistent local systems with less AI overhead.",
        "highlights": [
            {"title": "Dated multi-beat time skips", "example": "A month can show separate training, companion, communication, and world developments across the actual dates instead of one flattened result."},
            {"title": "Independent companion work", "example": "A companion assigned to maintain a shelter or investigate a lead can reach milestones while the player pursues something else."},
            {"title": "NPCs develop on their own", "example": "Recurring allies and rivals can train and grow from their own established goals without being scaled to the player."},
            {"title": "Ability evolution history", "example": "Opening a skill can show the applications and breakthroughs it has gained during this campaign."},
            {"title": "World-specific downtime", "example": "Bleach skips include division duties, while Naruto includes mission reports and village routines and Satisfy includes rankings and class opportunities."},
            {"title": "Messages that answer world events", "example": "Known contacts can send grounded reports or reactions after important developments without requiring another AI request."},
            {"title": "Lower prompt overhead", "example": "A local budget keeps the most relevant abilities, items, people, chats, and campaign facts in each AI request instead of resending unrelated save history."},
            {"title": "Targeted campaign recovery", "example": "Diagnostics can repair only the scene, combat, progression, abilities, NPCs, or world state that became malformed."},
            {"title": "Narrative Satisfy classes", "example": "Overgeared characters normally begin as Beginners and earn a class through story events, with optional Hidden or Legendary class starts still available."},
        ],
    },
    "3.40.0": {
        "title": "A More Consistent Game Master",
        "summary": "This update makes the GM better at remembering the live scene, carrying consequences forward, and keeping narration aligned with the character sheet.",
        "highlights": [
            {"title": "Stronger scene continuity", "example": "People remain where the story placed them, and the GM remembers the immediate danger, question, and objective."},
            {"title": "One-pass response repair", "example": "Incomplete or contradictory GM responses receive one targeted correction only when a local check proves it is needed."},
            {"title": "Narrative and mechanics agree", "example": "A claimed awakening, mastery, or transformation must leave an appropriately durable result."},
            {"title": "Canon changes keep changing canon", "example": "Prevented or altered events now carry their effects into dependent future events instead of snapping back to the original plot."},
            {"title": "Promises and delayed consequences persist", "example": "Debts, deadlines, betrayals, and long-term fallout can become due later instead of being forgotten after one turn."},
            {"title": "More varied pacing", "example": "The GM notices repeated combat, training, social, or travel beats and varies the next development through existing story threads."},
            {"title": "Advisor evidence", "example": "Advisor answers now include an expandable explanation of the campaign facts and current mechanics behind the answer."},
            {"title": "Lower lore overhead", "example": "Lore retrieval is skipped when the live campaign already contains enough evidence, while canon-heavy questions still receive source grounding."},
            {"title": "Learns from liked turns", "example": "Turns marked as good gently teach the GM your preferred detail and kinds of scenes without changing difficulty or outcomes."},
        ],
    },
}


def notes_for(version):
    notes = RELEASE_NOTES.get(str(version), {})
    return {"version": str(version), **notes} if notes else {"version": str(version), "title": "Worldwalker Updated", "summary": "A new version is ready.", "highlights": []}
