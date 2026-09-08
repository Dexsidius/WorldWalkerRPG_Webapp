"""Simulation reliability hotfix; save schema and base version remain stable."""
BUILD_ID = "3.64.0-world-ui-1"
PATCH_NOTES = {
    "title": "World-themed controls and motion",
    "summary": "Each world gains tailored button feedback, menu transitions and a themed cursor. Naruto and One Piece cursor artwork has been redrawn. All effects work locally and respect reduced motion.",
    "highlights": [
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
