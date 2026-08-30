"""Player-facing release notes shown once per browser/account and version."""

RELEASE_NOTES = {
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
