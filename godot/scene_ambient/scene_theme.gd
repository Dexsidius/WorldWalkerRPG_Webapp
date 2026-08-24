extends Node2D
## Reads ?category=<scene_category>&weather=<weather> from the embedding
## page's URL. Replaces the old canvas particle/glow system (seedParticles/
## tickSceneFx) and the CSS weather overlay (.scene-weather) with one
## layered Godot effect: a category-themed particle layer plus an
## independent weather particle layer on top, both able to be active at once
## (e.g. rain over a battlefield).

@onready var category_particles: GPUParticles2D = $CategoryParticles
@onready var weather_particles: GPUParticles2D = $WeatherParticles

# Grouped the same way the categories already read in-game (a torch-lit
# indoor hall isn't a battlefield isn't a forest) rather than one entry per
# category string — most of Worldwalker's ~19 scene categories collapse
# into a much smaller number of genuinely distinct moods.
const FAMILIES := {
	"warm_crowd": {
		"colors": [Color(1, 0.85, 0.55, 0), Color(1, 0.85, 0.55, 0.55), Color(1, 0.9, 0.65, 0.3), Color(1, 0.85, 0.55, 0)],
		"direction": Vector3(0, -1, 0), "spread": 35.0, "gravity": Vector3(0, -3, 0),
		"velocity": Vector2(2, 6), "scale": Vector2(0.3, 0.75), "amount": 22,
	},
	"duel_sparks": {
		"colors": [Color(1, 0.9, 0.5, 0), Color(1, 0.83, 0.42, 1), Color(1, 0.6, 0.2, 0.6), Color(1, 0.4, 0.1, 0)],
		"direction": Vector3(0, -1, 0), "spread": 180.0, "gravity": Vector3(0, 6, 0),
		"velocity": Vector2(20, 46), "scale": Vector2(0.15, 0.45), "amount": 20, "emission_radius": 6.0,
	},
	"forest": {
		"colors": [Color(0.72, 0.85, 0.35, 0), Color(0.78, 0.65, 0.25, 0.85), Color(0.6, 0.75, 0.3, 0.5), Color(0.72, 0.85, 0.35, 0)],
		"direction": Vector3(-0.6, 1, 0), "spread": 20.0, "gravity": Vector3(-4, 10, 0),
		"velocity": Vector2(3, 8), "scale": Vector2(0.4, 0.85), "amount": 20,
	},
	"stars": {
		"colors": [Color(1, 1, 1, 0), Color(1, 1, 1, 0.9), Color(0.85, 0.9, 1, 0.5), Color(1, 1, 1, 0)],
		"direction": Vector3(0.1, -0.05, 0), "spread": 60.0, "gravity": Vector3(0, 0, 0),
		"velocity": Vector2(0.5, 2), "scale": Vector2(0.12, 0.35), "amount": 36,
	},
	"cozy": {
		"colors": [Color(1, 0.82, 0.5, 0), Color(1, 0.78, 0.45, 0.6), Color(1, 0.85, 0.55, 0.35), Color(1, 0.82, 0.5, 0)],
		"direction": Vector3(0, -1, 0), "spread": 45.0, "gravity": Vector3(0, -2, 0),
		"velocity": Vector2(1.5, 5), "scale": Vector2(0.25, 0.6), "amount": 16,
	},
	"embers_warm": {
		"colors": [Color(1, 0.55, 0.15, 0), Color(1, 0.65, 0.2, 1), Color(1, 0.4, 0.1, 0.5), Color(0.5, 0.15, 0.05, 0)],
		"direction": Vector3(0, -1, 0), "spread": 22.0, "gravity": Vector3(0, -16, 0),
		"velocity": Vector2(8, 18), "scale": Vector2(0.2, 0.5), "amount": 26,
	},
	"embers_sick": {
		"colors": [Color(0.45, 1, 0.6, 0), Color(0.5, 1, 0.65, 0.9), Color(0.35, 0.85, 0.5, 0.45), Color(0.2, 0.4, 0.25, 0)],
		"direction": Vector3(0, -1, 0), "spread": 22.0, "gravity": Vector3(0, -14, 0),
		"velocity": Vector2(7, 16), "scale": Vector2(0.2, 0.5), "amount": 26,
	},
	"mist": {
		"colors": [Color(0.75, 0.9, 0.95, 0), Color(0.8, 0.93, 0.97, 0.4), Color(0.85, 0.95, 1, 0.22), Color(0.75, 0.9, 0.95, 0)],
		"direction": Vector3(0.4, -0.1, 0), "spread": 30.0, "gravity": Vector3(2, -0.5, 0),
		"velocity": Vector2(2, 6), "scale": Vector2(1.0, 1.9), "amount": 12,
	},
	"drips": {
		"colors": [Color(0.55, 0.75, 1, 0), Color(0.6, 0.8, 1, 0.85), Color(0.5, 0.7, 0.95, 0.5), Color(0.55, 0.75, 1, 0)],
		"direction": Vector3(0, 1, 0), "spread": 4.0, "gravity": Vector3(0, 60, 0),
		"velocity": Vector2(4, 10), "scale": Vector2(0.12, 0.3), "amount": 14,
	},
	"beams": {
		"colors": [Color(0.5, 0.85, 1, 0), Color(0.55, 0.9, 1, 0.8), Color(0.45, 0.8, 1, 0.4), Color(0.5, 0.85, 1, 0)],
		"direction": Vector3(0, -1, 0), "spread": 6.0, "gravity": Vector3(0, -10, 0),
		"velocity": Vector2(6, 14), "scale": Vector2(0.18, 0.4), "amount": 14,
	},
	"hall_glow": {
		"colors": [Color(1, 0.78, 0.4, 0), Color(1, 0.8, 0.45, 0.7), Color(1, 0.85, 0.55, 0.35), Color(1, 0.78, 0.4, 0)],
		"direction": Vector3(0, -1, 0), "spread": 50.0, "gravity": Vector3(0, -3, 0),
		"velocity": Vector2(1.5, 5), "scale": Vector2(0.3, 0.7), "amount": 18,
	},
}

const CATEGORY_TO_FAMILY := {
	"town_square": "warm_crowd", "kingdom": "warm_crowd", "arena_floor": "warm_crowd",
	"duel": "duel_sparks",
	"forest_path": "forest", "mountain_castle": "forest",
	"starry_sky": "stars", "night_wilderness": "stars",
	"merchant_shop": "cozy", "tavern_inn": "cozy", "academy_classroom": "cozy",
	"battlefield_dusk": "embers_warm",
	"monster_battlefield": "embers_sick", "monster_lair": "embers_sick",
	"harbor_port": "mist", "ship_deck": "mist",
	"dungeon_cave": "drips",
	"tower_hub": "beams",
	"indoor_grandhall": "hall_glow",
}

const WEATHER_THEMES := {
	"rain": {
		"colors": [Color(0.75, 0.85, 1, 0), Color(0.8, 0.88, 1, 0.6), Color(0.7, 0.82, 1, 0.4), Color(0.75, 0.85, 1, 0)],
		"direction": Vector3(0.15, 1, 0), "spread": 4.0, "gravity": Vector3(20, 340, 0),
		"velocity": Vector2(10, 20), "scale": Vector2(0.25, 0.6), "amount": 70,
	},
	"storm": {
		"colors": [Color(0.6, 0.7, 0.85, 0), Color(0.68, 0.76, 0.9, 0.75), Color(0.55, 0.65, 0.8, 0.5), Color(0.6, 0.7, 0.85, 0)],
		"direction": Vector3(0.35, 1, 0), "spread": 6.0, "gravity": Vector3(60, 520, 0),
		"velocity": Vector2(16, 30), "scale": Vector2(0.28, 0.65), "amount": 110,
	},
	"snow": {
		"colors": [Color(1, 1, 1, 0), Color(1, 1, 1, 0.85), Color(0.95, 0.97, 1, 0.5), Color(1, 1, 1, 0)],
		"direction": Vector3(0.05, 1, 0), "spread": 30.0, "gravity": Vector3(0, 22, 0),
		"velocity": Vector2(3, 8), "scale": Vector2(0.3, 0.7), "amount": 46,
	},
	"fog": {
		"colors": [Color(0.82, 0.85, 0.88, 0), Color(0.85, 0.87, 0.9, 0.32), Color(0.82, 0.85, 0.88, 0.18), Color(0.82, 0.85, 0.88, 0)],
		"direction": Vector3(0.5, 0, 0), "spread": 15.0, "gravity": Vector3(0, 0, 0),
		"velocity": Vector2(3, 8), "scale": Vector2(1.6, 2.6), "amount": 10,
	},
}

var _last_theme_key := ""
var _poll_timer := 0.0

# The emitters below were hand-placed in scene_ambient.tscn assuming this
# exact canvas size. window/stretch/aspect="expand" (project.godot) grows
# the live viewport past this whenever the embedding container's aspect
# ratio differs from it — which it always does, since every scene banner
# size on the page is wider/narrower than this fixed design canvas — so
# without rescaling, the emitters would stay pinned to their original small
# patch instead of covering the actual, larger visible area.
const _DESIGN_SIZE := Vector2(640, 260)

func _ready() -> void:
	var params := _query_params()
	_last_theme_key = params.get("category", "") + "::" + params.get("weather", "")
	set_theme(params.get("category", ""), params.get("weather", ""))
	_fit_to_viewport()
	get_viewport().size_changed.connect(_fit_to_viewport)

func _fit_to_viewport() -> void:
	var vp := get_viewport_rect().size
	if vp.x <= 0 or vp.y <= 0:
		return
	var sx := vp.x / _DESIGN_SIZE.x
	var sy := vp.y / _DESIGN_SIZE.y
	var s: float = max(sx, sy)
	category_particles.position = Vector2(vp.x * 0.5, vp.y * (170.0 / _DESIGN_SIZE.y))
	var cat_mat := category_particles.process_material as ParticleProcessMaterial
	if cat_mat:
		cat_mat.emission_sphere_radius = 260.0 * s
	weather_particles.position = Vector2(vp.x * 0.5, -10.0 * sy)
	var weather_mat := weather_particles.process_material as ParticleProcessMaterial
	if weather_mat:
		weather_mat.emission_box_extents = Vector3(340.0 * sx, 2.0, 0.0)

func _process(delta: float) -> void:
	# A JS eval() round-trip every single frame is wasteful for something
	# that only actually changes once per player turn — a few times a
	# second is plenty responsive.
	_poll_timer += delta
	if _poll_timer < 0.35:
		return
	_poll_timer = 0.0
	# The scene banner changes almost every turn — reloading this ~40MB WASM
	# runtime on every single one (the naive approach: just change the
	# iframe's src) would mean a multi-second reload flicker constantly.
	# JavaScriptBridge.create_callback()/get_interface() to expose a
	# Godot-side function to JS proved unreliable in practice (calls landed
	# nowhere, silently, no error) — polling a plain JS global via eval()
	# is the same primitive the initial query-string read already uses
	# successfully, so it reuses a path already proven to work instead of a
	# second, flakier one. app.js sets window.sceneThemeParams; this just
	# notices when it changes.
	if not OS.has_feature("web"):
		return
	var raw: String = JavaScriptBridge.eval("window.sceneThemeParams || ''", true)
	if raw == "" or raw == _last_theme_key:
		return
	_last_theme_key = raw
	var parts := raw.split("::")
	set_theme(parts[0] if parts.size() > 0 else "", parts[1] if parts.size() > 1 else "")

func set_theme(category: String, weather: String) -> void:
	_apply(category_particles, FAMILIES.get(CATEGORY_TO_FAMILY.get(category, ""), FAMILIES["stars"]))
	var weather_theme: Variant = WEATHER_THEMES.get(weather)
	if weather_theme:
		weather_particles.emitting = true
		_apply(weather_particles, weather_theme)
	else:
		weather_particles.emitting = false

func _query_params() -> Dictionary:
	var result := {}
	if not OS.has_feature("web"):
		return result
	var query: String = JavaScriptBridge.eval("window.location.search", true)
	if typeof(query) != TYPE_STRING:
		return result
	for pair in query.trim_prefix("?").split("&"):
		var kv := pair.split("=")
		if kv.size() == 2:
			result[kv[0]] = kv[1].uri_decode()
	return result

func _apply(node: GPUParticles2D, theme: Dictionary) -> void:
	var mat := node.process_material as ParticleProcessMaterial
	if mat == null:
		return
	var ramp := Gradient.new()
	ramp.offsets = PackedFloat32Array([0.0, 0.15, 0.8, 1.0])
	ramp.colors = theme["colors"]
	var ramp_tex := GradientTexture1D.new()
	ramp_tex.gradient = ramp
	mat.color_ramp = ramp_tex
	mat.direction = theme["direction"]
	mat.spread = theme["spread"]
	mat.gravity = theme["gravity"]
	mat.initial_velocity_min = theme["velocity"].x
	mat.initial_velocity_max = theme["velocity"].y
	mat.scale_min = theme["scale"].x
	mat.scale_max = theme["scale"].y
	if theme.has("emission_radius"):
		mat.emission_sphere_radius = theme["emission_radius"]
	node.amount = int(theme.get("amount", 20))
