"""Simulation reliability hotfix; save schema and base version remain stable."""
BUILD_ID = "3.64.0-offline-living-world-2"
PATCH_NOTES = {
    "title": "Offline living world — timing and recapture fixes",
    "summary": "Scheduled offline decisions now resolve chronologically, and recaptures face the current holding's owner and garrison. Existing saves are preserved; unknown defenses remain unknown. Main AI play remains available. Broader canon and political content is still in development.",
    "highlights": [
        {"title": "Consistent time skips", "example": "A petition due before Arlong's defeat is decided under the occupation, even if one time skip also crosses his later defeat. Splitting the same time into days gives the same result."},
        {"title": "Fight the actual occupier", "example": "Recapturing a holding checks its current owner and committed garrison, not the former owner's weaker defenses. Stale plans are rejected; unknown old-save garrisons are not invented."},
        {"title": "Government decisions without AI", "example": "Established local governments budget for public works and order every campaign week. Time skips and save/reload preserve the same decisions; local reports explain what was funded."},
        {"title": "Plan a local campaign", "example": "Muster present members with recorded strength, survey an established garrison, then commit forces and pay for supplies. Unknown forces remain unknown; armies cannot teleport or be reused immediately."},
        {"title": "Rescue is not conquest", "example": "Protecting villagers does not itself defeat Arlong. Canon aftermath resolves separately and does not overwrite land already captured by someone else."},
        {"title": "Three local intervention encounters", "example": "Protect Duy’s team before the Eighth Gate, protect villagers at Arlong Park, or cover Rukia’s retreat at Sokyoku Hill. Arrive within the intervention window; success requires the tactical objective."},
        {"title": "Support is not sovereignty", "example": "Offline civic activities build local support. Advisory petitions receive scheduled responses; military victories secure one foothold before a separate local-government charter."},
        {"title": "Optional map animation", "example": "Known event participants can be selected on the map. Instant movement defaults on touch devices and does not stop the simulation."},
        {"title": "World-specific interactions", "example": "Menu entrances, button edges and press feedback fit the active world without delaying actions."},
        {"title": "Clearer themed cursors", "example": "A faceted Naruto kunai and broad-grinning straw-hat skull replace the earlier simplified cursors; remaining worlds have their own motifs."},
        {"title": "Accessible on desktop and phone", "example": "Keyboard focus stays visible, disabled controls stay still, touch has press feedback and reduced motion removes new animation."},
        {"title": "Approved richer colors", "example": "Map scenery has 30% more saturation and slightly stronger contrast. Text, portraits and interface colors remain unchanged."},
        {"title": "World-specific scenery", "example": "Naruto villages and One Piece islands have distinct terrain and landmark silhouettes."},
        {"title": "Zoom reveals detail", "example": "Smaller building details and tree trunks appear as you zoom closer."},
        {"title": "Campaign map preserved", "example": "Ownership colors use the existing campaign atlas; markers, search, mobile navigation and travel remain available."},
        {"title": "Works locally in both editions", "example": "The renderer and dependencies are bundled; no AI requests or online asset downloads are required."},
    ],
}
