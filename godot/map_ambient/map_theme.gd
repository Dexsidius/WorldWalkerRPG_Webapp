extends Node2D
## Two purely atmospheric layers over the existing map (which already
## handles the real interactive parts — pan/zoom, territory coloring,
## clickable pins — untouched): slow drifting cloud-shadows for a sense of
## a living map, and a pulsing glow at any landmark dangerous enough to
## warrant standing out on the atlas at a glance. Danger-node positions
## come from ?danger=<json> in the embedding URL, read once at startup —
## unlike the scene banner, #map-wrap (and this iframe with it) is a fresh
## DOM element every time the Map tab renders, so a fresh load each time is
## already what happens; no live-update mechanism is needed here.

@onready var cloud_particles: GPUParticles2D = $CloudParticles

var danger_nodes: Array = []
var pulse_t := 0.0

func _ready() -> void:
	if not OS.has_feature("web"):
		return
	var query: String = JavaScriptBridge.eval("window.location.search", true)
	if typeof(query) != TYPE_STRING:
		return
	for pair in query.trim_prefix("?").split("&"):
		var kv := pair.split("=")
		if kv.size() == 2 and kv[0] == "danger":
			var parsed: Variant = JSON.parse_string(kv[1].uri_decode())
			danger_nodes = parsed if parsed is Array else []

func _process(delta: float) -> void:
	pulse_t += delta
	if not danger_nodes.is_empty():
		queue_redraw()

func _draw() -> void:
	if danger_nodes.is_empty():
		return
	var vp := get_viewport_rect().size
	for entry in danger_nodes:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var px: float = float(entry.get("x", 50)) / 100.0 * vp.x
		var py: float = float(entry.get("y", 50)) / 100.0 * vp.y
		# Each marker pulses on its own slightly offset phase (seeded from
		# its position) so a cluster of dangerous locations doesn't all
		# throb in lockstep.
		var pulse := 0.55 + sin(pulse_t * 2.0 + px * 0.05 + py * 0.03) * 0.45
		var radius := 12.0 + pulse * 5.0
		draw_circle(Vector2(px, py), radius * 2.2, Color(1, 0.32, 0.16, 0.05 + pulse * 0.05))
		draw_circle(Vector2(px, py), radius * 1.3, Color(1, 0.36, 0.18, 0.10 + pulse * 0.10))
		draw_circle(Vector2(px, py), radius * 0.5, Color(1, 0.45, 0.2, 0.18 + pulse * 0.18))
