"""Approved Dream map art and device-local graphics quality, shared by both editions."""
BUILD_ID = "3.64.0-dream-mobile-1"
PATCH_NOTES = {
    "title": "Richer world maps, lighter phone combat",
    "summary": "Approved Naruto and One Piece scenery now uses the live campaign map. Choose High for the 3D artwork or Low for the lightweight 2D atlas. Auto defaults to Low on phones.",
    "highlights": [
        {"title": "The approved world scenery", "example": "Textured Naruto mountains, forests and villages; One Piece islands, Red Line cliffs, ports and ambient ocean movement. Current campaign ownership still supplies borders and control colors."},
        {"title": "Graphics that suit your device", "example": "The map and combat have an Auto / High / Low selector. Low removes 3D map rendering and heavy attack sheets, while retaining locations, targeting, portraits and outcomes. The choice stays on this browser."},
        {"title": "Lighter phone battles", "example": "Low mode caps combat canvases at 768 pixels on their longest edge, uses simple impact highlights, and skips large Unity sprite downloads. Your ability range, turn order, movement and damage do not change."},
        {"title": "Less work between actions", "example": "Unchanged combat snapshots no longer rebuild the board, static terrain is cached, and hidden combat pages do not poll. Static map buildings are batched; offscreen scenery pauses and Low releases its renderer."},
        {"title": "Shared main and offline", "example": "Both editions use the same map and combat code. Main keeps AI and written actions outside tactical battles. No save conversion or paid model calls are needed for these graphics."}
    ],
}
