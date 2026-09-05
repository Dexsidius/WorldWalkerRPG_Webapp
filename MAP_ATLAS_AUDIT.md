# Political atlas — v3.59.0

## What is guaranteed

- Every displayed surface-land tile has exactly one preset controller, independent of character start. Presets never use the player's location as a geography seed.
- The coastline, tiles, labels and location markers share a normalized coordinate system. The renderer uses vectors rather than a differently cropped picture beneath markers.
- Location control changes and explicit narrative claims overlay the baseline. One-tile player holdings grow contiguously on their landmass. Adjacent identical controllers lose their internal boundary.
- Saves retain their authored political changes; viewing the map does not rewrite a save. Unknown unanchored claims are not teleported to the player.
- Bleach boards are independent; Solo exposes the current floor only. No extra timeline dates or travel destinations were added.
- Map geometry stays local and is not sent to the GM. The GM receives compact claim facts, including exact tile counts and realm/board identifiers.

## Canon and approximation decisions

These are **schematic game atlases**, not reproductions of official survey maps. Coastline detail, exact national borders, map distances, island sizes and many uncertain placements are authored approximations. They must not be described as fully canon-verified. The underlying travel system keeps its established durations; the map is not a distance ruler.

| World | Baseline and correction | Deliberate concession |
|---|---|---|
| Naruto | Earth northwest, Wind southwest, Fire central, Lightning northeast, Water offshore east; Rain between the large western/central countries. Grass and Waterfall no longer reversed. | Minor borders and coastlines are schematic. Village controllers stand for their countries' operational authority; this does not abolish daimyo in the story. Waves and Whirlpools are separate islands. Scenario/dimensional markers are not surface countries. |
| One Piece | Separate islands on a sea-route chart; Red Line and Grand Line orientation, enlarged island footprints. Ryugu sovereignty is separate from Whitebeard protection. | Island spacing is strongly compressed for readability. Moving vessels, sky islands and undersea locations remain markers, not surface land. Unmapped Red Line is assigned to World Government for play. Occupied Wano and Totto Land reflect baseline faction control; changes in a campaign override it. |
| HxH | NGL west and East Gorteau east within the Mitene/Balsa island group south of Yorbian mainland; Kakin and Padokea separate. | Exact positions of undisclosed sites, the Exam, Meteor City and the Association are schematic. Unspecified mainland districts use civic/regional authorities rather than falsely assigning whole countries to the Mafia or Phantom Troupe. |
| Overgeared | Pangea moved to the East Continent; Eternal holdings and Saharan land occupy the West Continent. Reidan remains western Eternal at baseline. | Exact coastlines and borders are inferred; Behen is enlarged. Eternal does not automatically become the player's kingdom because of a particular start. |
| Slime | Falmuth west/northwest of Jura; Dwargon along northern mountains; Eastern Empire east; Thalion southwest. | Nation footprints and disputed/unmapped hinterlands are schematic. Tempest is represented by a local footprint instead of automatically owning all Jura. |
| Bleach | Independent Soul Society, Living World, Hueco Mundo, Royal Realm and Hell maps. | Soul Society is one sovereign surface territory, not separate countries for every barracks. Hueco Mundo's hinterland uses Hollow dominions and Las Noches court without revealing Aizen prematurely. Realm silhouettes are schematics; underground/hidden sites are markers. |
| JJK | Japan's four main islands remain under civil Japan; schools, clans and colonies are sites, not sovereign countries. | Simplified Japan outline. Barriers do not change sovereignty by themselves; genuine territorial changes still can. |
| Solo | Only Earth or the current floor is returned, with tower administration as the floor baseline. | Detailed floor-specific terrain is **not complete**. Current floor boards are explicitly labeled schematic. No invented canonical floor layouts are claimed. |
| Custom | Stable local/regional baseline, replaced by narrative claims. | Generic geography is authored game content, not external canon. |

## Reference checks

- [Naruto geography](https://naruto.fandom.com/wiki/Geography), [Five Great Shinobi Countries](https://naruto.fandom.com/wiki/Five_Great_Shinobi_Countries): relative country arrangement, not exact borders.
- [One Piece setting](https://en.wikipedia.org/wiki/One_Piece): seas, Red Line and Grand Line. Island government/protection distinctions retained separately.
- [Mitene Union](https://hunterxhunter.fandom.com/wiki/Mitene_Union): Balsa Islands south of Yorbian, NGL and East Gorteau in the same union.
- [Eternal Kingdom](https://overgeared.fandom.com/wiki/Eternal_Kingdom), [Reidan](https://overgeared.fandom.com/wiki/Reidan): western desert holding and political affiliation.
- [Magic Continent](https://tensura.fandom.com/wiki/Magic_Continent), [Falmuth](https://tensura.fandom.com/wiki/Kingdom_of_Falmuth): Jura's regional relationships.
- [Three Worlds](https://bleach.fandom.com/wiki/Three_Worlds): separate dimensions, not neighboring surface countries.
- [Culling Game colonies](https://jujutsu-kaisen.fandom.com/wiki/Culling_Game/Colonies): barriers and Hokkaido's special status, not civil sovereignty.

## Follow-up improvements worth considering

1. **Scenario-aware baseline dates:** presets are deliberately start-independent; a future era overlay could make a historical date change the starting ruler without affecting location geometry. Existing narrative ownership overrides already work.
2. **True regional inset maps:** vector zoom is sharp and reveals finer markers, but it does not invent street/building-level geography. Authored city insets would make close zoom much more useful.
3. **Occupation versus sovereignty layer:** a second optional layer could show a pirate protector or military occupier separately from the kingdom itself. This avoids conflating diplomacy and annexation.
4. **Floor authoring pass:** Solo needs genuinely distinct floor terrain and known local domains. Current-floor isolation is ready; claiming all fifty detailed floor maps are finished would be inaccurate.

These are suggestions, not additional simulations silently added in this patch.
