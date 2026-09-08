# World interaction polish

CSS-only shared enhancement for main and offline. Existing controls and event handlers remain authoritative; no actions are intercepted, delayed, or replayed. Native select option popups remain OS-rendered. Map markers are excluded from press/hover movement so coordinates stay stable.

Each world has its own motion timing, menu entrance, button corner treatment and cursor. Cursor graphics use native browser cursors, with no mouse-following canvas. Text fields keep text cursors, the map retains grab/grabbing, and disabled buttons remain identifiable. Touch devices do not get simulated cursors or hover movement. Reduced motion removes new animations and transitions.

The Naruto and One Piece vectors are reference-guided redraws, not extracted official art. References consulted: https://fr.naruto.wikia.com/wiki/Kuna%C3%AF and https://wallpapersafari.com/one-piece-jolly-roger-wallpaper/ . Existing Bleach and JJK cursors are retained. New original motif cursors cover the remaining worlds. All assets stay local and are under 48 pixels at native cursor size.

No Three.js is needed for buttons or dialogs. Avoiding an additional graphics context keeps these effects inexpensive on phones. Existing world art, typography, map saturation and gameplay are unchanged.
