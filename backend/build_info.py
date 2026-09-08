"""Simulation reliability hotfix; save schema and base version remain stable."""
BUILD_ID = "3.64.0-gameplay-integrity-3"
PATCH_NOTES = {
    "title": "Reliable rewards, orders and world outcomes",
    "summary": "Military outcomes require evidence; income and mastery no longer depend on repeated messages or requests. Completed plans make room for new goals, infirmaries improve rest, and local simulation failures are reported safely.",
    "highlights": [
        {"title": "No unsupported background conquest", "example": "Old faction battles and newer military operations share one resolver; missing forces, defenses, access or supplies leave the outcome pending."},
        {"title": "Accurate passive income", "example": "Splitting one hour into short actions earns the same proceeds; fractions are retained and retries cannot pay the same interval twice."},
        {"title": "Long-campaign plans", "example": "Finished plans are archived without blocking new plans or forgetting their dependency outcomes."},
        {"title": "Earned mastery", "example": "Failed or merely mentioned techniques do not grant mastery; completed training segments and confirmed successful uses do."},
        {"title": "Useful infirmaries", "example": "Each local infirmary level improves ordinary rest recovery by 12%, shown before confirming the action."},
        {"title": "Safe organization orders", "example": "Orders have retry receipts, stale-state checks and rollback protection; subsystem failures preserve prior state and appear in Diagnostics."},
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
