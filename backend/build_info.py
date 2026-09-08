"""Simulation reliability hotfix; save schema and base version remain stable."""
BUILD_ID = "3.64.0-shared-maps-2"
PATCH_NOTES = {
    "title": "Richer Naruto and One Piece map colors",
    "summary": "Naruto and One Piece gain local 3D terrain and regional landmarks beneath the existing campaign map controls. Main and offline share the same renderer; unsupported browsers retain the vector atlas.",
    "highlights": [
        {"title": "Approved richer colors", "example": "Map scenery has 30% more saturation and slightly stronger contrast. Text, portraits and interface colors remain unchanged."},
        {"title": "World-specific scenery", "example": "Naruto villages and One Piece islands have distinct terrain and landmark silhouettes."},
        {"title": "Zoom reveals detail", "example": "Smaller building details and tree trunks appear as you zoom closer."},
        {"title": "Campaign map preserved", "example": "Ownership colors use the existing campaign atlas; markers, search, mobile navigation and travel remain available."},
        {"title": "Works locally in both editions", "example": "The renderer and dependencies are bundled; no AI requests or online asset downloads are required."},
    ],
}
