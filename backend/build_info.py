"""Simulation reliability hotfix; save schema and base version remain stable."""
BUILD_ID = "3.64.0-simulation-reliability-2"
PATCH_NOTES = {
    "title": "More reliable world operations and training",
    "summary": "Faction operations follow campaign time, concealed operations stay out of player panels, and assignments and mentors recheck availability. Existing campaigns use these fixes automatically.",
    "highlights": [
        {"title": "Time, not button presses", "example": "Faction operations accumulate one preparation point per six campaign hours, retain partial time, and do not count the same interval twice."},
        {"title": "Preparation is not conquest", "example": "A military operation at 100% awaits an evidence-based GM resolution instead of automatically taking territory."},
        {"title": "Concealed operations stay concealed", "example": "Explicitly hidden operations are filtered from player state, panels, local interventions, and generated operation news."},
        {"title": "Available people only", "example": "A dead, missing or no-longer-commandable member stops an assignment without a reward; absent mentors cannot complete a training session."},
        {"title": "One membership source of truth", "example": "Official members come from the organization ledger for the Team screen, GM context, Advisor context, commands, and faction-roster mirror."},
        {"title": "Old-save roster repair", "example": "Places and organizations such as Amegakure or Akatsuki are removed when they were accidentally stored as member names; legitimate character-backed members are recovered once."},
        {"title": "Candidates are not members", "example": "Invitations, recruitment attempts, affiliates, and refused offers do not appear as official party members until the engine-owned Yes/No decision establishes membership."},
        {"title": "Relationships do not imply membership", "example": "High affinity, a contact record, being in the same location, or appearing in old prose can no longer put an entity on a team."},
        {"title": "Recruitment prompts remain authoritative", "example": "Future named recruits and player join requests still use the explicit local confirmation system from the previous hotfix."},
    ],
}
