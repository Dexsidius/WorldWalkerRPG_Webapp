"""Player-facing release notes shown once per browser/account and version."""

RELEASE_NOTES = {
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
