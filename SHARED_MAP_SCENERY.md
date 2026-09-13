# Shared Naruto and One Piece scenery

Both editions use `frontend/js/atlas-scenery.js`, mounted by the existing atlas controller. Three.js 0.180.0 and its MIT license are bundled in `frontend/vendor/three`. No CDN, AI call, new POST route or save schema is introduced.

The production view deliberately keeps the existing atlas projection and camera controls. 3D elevation projects above the same ground coordinates; DOM locations, routes, player/NPC markers, selection, search and zoom remain controlled by the existing game. It is not a separate interactive map or a copy of the offline prototype. The standalone orbit previews remain art studies, not alternate campaign engines.

Naruto has country-specific terrain, forest clusters, village silhouettes and landmark features. One Piece uses its own island geometry, terrain and island-specific architecture (Drum, Alabasta, Water 7, Wano, Sabaody, Marine fortifications and others). Some smaller places intentionally use generic port architecture. Detailed canonical likenesses are not claimed.

Ownership tint and border segments come from the supplied current `atlas.cells`, never from a fixed Naruto ownership overlay. Country authority versus village command and kingdom/protector context remain the backend atlas's responsibility. This change does not rewrite those rules. Shading rebuilds with each campaign atlas refresh.

WebGL loading is optional: the original SVG remains mounted until a frame successfully renders, and returns after context loss. The device-local Graphics selector offers Auto, High and Low. Auto selects Low on viewports at most 850px wide or connections requesting reduced data. Low never imports the 3D renderer, removes existing scenery and keeps the interactive SVG map. It also reduces tactical effects without changing combat rules. The preference is shared between the map and combat, not stored in a campaign.

High uses the approved Dream Loop terrain and architecture atlases in `assets/dream-map`, with world-specific scene builders and batched static architecture. Terrain uses the authoritative atlas land polygons, and current ownership cells supply tint and borders; preview-only coast edits, labels and campaign fixtures are not shipped. Rendering is resolution-capped, throttled to approximately 15fps, paused in hidden/offscreen views and disposed when its map plane is removed. Zoom adjusts raster resolution within that cap; detailed geometry currently remains loaded throughout High mode rather than using streaming LOD. Main and offline use identical assets and behavior.

Validation includes the full main and offline suites plus real-browser regressions in `tests/test_atlas_scenery_browser.py` and `tests/test_mobile_graphics_browser.py`. Both Windows editions must pass the paired packager before publication. Physical-phone GPU performance still varies by device; responsive browser tests do not replace physical-device benchmarks, and the vector fallback is retained.
