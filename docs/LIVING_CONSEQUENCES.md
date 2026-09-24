# Living Consequences — build 3.64.0-living-consequences-1

## What happens in play

- Win the authored protection objective for Yahiko, Ace or Rukia. The rescue
  records a confirmed survival or escape fact, not a victory over the whole
  conflict. The next local follow-up opens one in-game hour later and lasts
  three days. The location activity list offers a short conversation, a
  one-hour practical contribution, or a no-penalty departure. A day later,
  a second local choice offers two distinct practical directions, such as
  relief versus testimony for Yahiko. A long activity in that same location
  pauses at either decision window's opening.
- In Naruto, Yahiko's people can regroup around Rain relief work. His survival
  removes the original grief-driven premise for the specified Jiraiya/Pain
  continuations; it does not make Hanzō harmless or settle Rain politics.
- In One Piece, Ace can regroup with retreating allies. Luffy's original
  death-driven training decision is no longer automatic, but Rayleigh can
  still offer training and the Marineford war is not awarded as a victory.
- In Bleach, Rukia remains free after the failed detention. The original
  accelerated execution and Sokyoku reveal cannot replay unchanged. The
  underlying Soul Society order and Aizen's intentions remain unresolved.
- NPC recovery goals advance privately if the player leaves. The Chronicle
  does not publish a private follow-up that the player did not witness.

## Rules and boundaries

Naruto, One Piece and Bleach now use authored event prerequisites instead of
automatically making each neighboring timeline entry depend on the previous
one. An established rescue affects its named dependent scenes; unrelated
events remain on the calendar. The GM and Advisor receive a compact, confirmed
rescue fact without receiving private appointment times or routes.

Existing save schema 21 is unchanged. Older saves with a completed authored
protection objective enroll the follow-up at the original recorded rescue
minute. Older saves that have only a rumor or unverified text do not gain an
invented rescue. Past canon events are not replayed.

This patch authors three specific two-stage aftermaths. It does not claim that all 119
canon entries have alternate story arcs, that later factions make fully
simulated political choices, or that a one-hour task changes a national
government, rank or friendship. Those outcomes remain subject to later play.

## Verification

`tests/test_canon_consequences.py` covers all three rescues, exact local
activity time, duplicate prevention, old-save enrollment, no remote privacy
leak, split-time/save-reload determinism, AI grounding and causal graph
precision. The prior canon appointment suite remains a regression gate.
