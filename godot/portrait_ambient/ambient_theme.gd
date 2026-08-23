extends Node2D
## Reads ?world=<Name> from the embedding page's URL and re-shapes the
## particle material to match that world's mood — same single export,
## no need to ship a separate ~40MB WASM build per world.

@onready var particles: GPUParticles2D = $AmbientParticles

const DEFAULT_THEME := {
	"colors": [Color(1, 0.92, 0.7, 0), Color(1, 0.92, 0.7, 0.85), Color(1, 0.95, 0.8, 0.5), Color(1, 1, 0.9, 0)],
	"direction": Vector3(0, -1, 0), "spread": 30.0, "gravity": Vector3(0, -6, 0),
	"velocity": Vector2(6, 16), "scale": Vector2(0.35, 0.9),
}

# Deliberately impressionistic, not literal — a small background layer at
# low opacity behind the portrait reads by color/motion/scale, not by
# precise shape (the shared soft round texture stays the same everywhere).
const THEMES := {
	"Naruto": {
		# Cherry blossom petals: warm pink, drifting down and sideways,
		# larger and slower than a spark.
		"colors": [Color(1, 0.85, 0.9, 0), Color(1, 0.78, 0.85, 0.9), Color(1, 0.7, 0.8, 0.6), Color(1, 0.85, 0.9, 0)],
		"direction": Vector3(0.35, 1, 0), "spread": 22.0, "gravity": Vector3(5, 12, 0),
		"velocity": Vector2(4, 9), "scale": Vector2(0.5, 1.05),
	},
	"One Piece": {
		# Sea mist: pale blue-white, large, slow, barely drifting — fog,
		# not particles with a clear trajectory.
		"colors": [Color(0.75, 0.9, 0.95, 0), Color(0.8, 0.93, 0.97, 0.5), Color(0.85, 0.95, 1, 0.3), Color(0.75, 0.9, 0.95, 0)],
		"direction": Vector3(0.4, -0.15, 0), "spread": 35.0, "gravity": Vector3(2, -1, 0),
		"velocity": Vector2(3, 8), "scale": Vector2(0.9, 1.7),
	},
	"Hunter x Hunter": {
		# Aura wisps: teal-green, tight upward stream, small and quick.
		"colors": [Color(0.4, 1, 0.75, 0), Color(0.45, 1, 0.8, 0.8), Color(0.5, 0.95, 0.85, 0.4), Color(0.4, 1, 0.75, 0)],
		"direction": Vector3(0, -1, 0), "spread": 16.0, "gravity": Vector3(0, -12, 0),
		"velocity": Vector2(7, 15), "scale": Vector2(0.28, 0.65),
	},
	"Solo Max-Level Newbie": {
		# System sparks: cyan-blue, fast, tight, small — glitchy energy.
		"colors": [Color(0.4, 0.85, 1, 0), Color(0.5, 0.9, 1, 0.95), Color(0.3, 0.75, 1, 0.55), Color(0.4, 0.85, 1, 0)],
		"direction": Vector3(0, -1, 0), "spread": 8.0, "gravity": Vector3(0, -4, 0),
		"velocity": Vector2(11, 24), "scale": Vector2(0.18, 0.5),
	},
	"Overgeared": {
		# Forge embers: orange-red, shooting upward fast, fading to ash.
		"colors": [Color(1, 0.6, 0.15, 0), Color(1, 0.7, 0.2, 1), Color(1, 0.45, 0.1, 0.5), Color(0.5, 0.2, 0.05, 0)],
		"direction": Vector3(0, -1, 0), "spread": 18.0, "gravity": Vector3(0, -20, 0),
		"velocity": Vector2(9, 19), "scale": Vector2(0.22, 0.55),
	},
	"Reincarnated as a Slime": {
		# Magicule sparkles: violet-blue, twinkly, wide and slow drift.
		"colors": [Color(0.6, 0.5, 1, 0), Color(0.7, 0.55, 1, 0.9), Color(0.55, 0.75, 1, 0.5), Color(0.6, 0.5, 1, 0)],
		"direction": Vector3(0, -1, 0), "spread": 45.0, "gravity": Vector3(0, -3, 0),
		"velocity": Vector2(3, 7), "scale": Vector2(0.28, 0.68),
	},
}

func _ready() -> void:
	apply_theme(THEMES.get(_world_from_query(), DEFAULT_THEME))

func _world_from_query() -> String:
	if not OS.has_feature("web"):
		return ""
	var query: String = JavaScriptBridge.eval("window.location.search", true)
	if typeof(query) != TYPE_STRING:
		return ""
	for pair in query.trim_prefix("?").split("&"):
		var kv := pair.split("=")
		if kv.size() == 2 and kv[0] == "world":
			return kv[1].uri_decode()
	return ""

func apply_theme(theme: Dictionary) -> void:
	var mat := particles.process_material as ParticleProcessMaterial
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
