"""AI portrait generation, identity-preserving updates, and disk caching.

Portraits are deliberately keyed only by visually relevant campaign state.
Ordinary turns do not spend another image request; appearance, form, clothing,
equipment, age, or other major visual changes do.
"""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import shutil
from pathlib import Path

from util import DATA_DIR, ASSET_ROOT, safe_filename, world_slug, ai_text


PORTRAIT_CACHE_DIR = DATA_DIR / "portraits"
PORTRAIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Rough $/image estimates for cloud portrait generation at 1024x1024, by
# quality tier. Unlike MODEL_PRICING_PER_1M in ai_client.py these are not
# pulled from a metered `usage` field (the Images API doesn't return one) —
# they're a flat per-call estimate, so treat the total as directional, not
# exact. Local image generation is always free.
PORTRAIT_COST_ESTIMATE_USD = {"low": 0.02, "medium": 0.07, "high": 0.19, "auto": 0.07}

_portrait_usage = {"generated": 0, "cost_usd": 0.0}


def portrait_usage():
    return dict(_portrait_usage)


def _record_portrait_usage(provider, quality):
    _portrait_usage["generated"] += 1
    if provider == "cloud":
        _portrait_usage["cost_usd"] += PORTRAIT_COST_ESTIMATE_USD.get(quality, 0.07)

WORLD_PORTRAIT_STYLES = {
    "One Piece": (
        "whimsical high-energy ocean adventure manga; exaggerated but appealing anatomy; "
        "eccentric readable silhouette; bold variable black ink; flat saturated cel colors; "
        "playful expressive facial construction"
    ),
    "Naruto": (
        "dynamic hand-inked ninja action manga; angular clean silhouette; restrained earth colors "
        "with one vivid accent; crisp cel shading; expressive eyes and practical shinobi design"
    ),
    "Hunter x Hunter": (
        "crisp strategic adventure manga; clean variable ink lines; bold simple color shapes; "
        "natural expressive face; subtle crosshatching; energetic but grounded"
    ),
    "Solo Max-Level Newbie": (
        "premium Korean action webtoon; semi-realistic anatomy; precise digital linework; smooth "
        "layered cel shading; dramatic luminous system accents and polished finish"
    ),
    "Overgeared": (
        "high-detail Korean fantasy webtoon; heroic semi-realistic anatomy; richly rendered metal, "
        "leather, and cloth; crisp digital linework; warm cinematic highlights"
    ),
    "Reincarnated as a Slime": (
        "vibrant modern isekai anime; friendly expressive character design; clean graceful linework; "
        "luminous soft cel shading; jewel-like magical color accents"
    ),
    "Custom World": (
        "cinematic anime-inspired RPG concept illustration; elegant ink contours; painterly cel "
        "shading; detailed materials; distinctive original silhouette"
    ),
}

WORLD_BACKDROPS = {
    "One Piece": "subdued turquoise ocean and bright sky with distant sails",
    "Naruto": "subdued mountain village rooftops, forest haze, and warm late-afternoon light",
    "Hunter x Hunter": "subdued wilderness trail meeting a distant modern city",
    "Solo Max-Level Newbie": "dark crystalline tower hall with faint cyan rings and no readable text",
    "Overgeared": "medieval forge workshop with amber furnace glow",
    "Reincarnated as a Slime": "great forest settlement with warm wooden roofs and magical motes",
    "Custom World": "misty crossroads where forest, city, mountains, and stars blend softly",
}

VISUAL_SPECIAL_KEYS = re.compile(
    r"species|race|form|transformation|evolution|clan|bloodline|devil fruit|class|body|eyes|hair|mark|curse|mutation",
    re.I,
)


def campaign_portrait_id(state):
    explicit = str(state.get("campaign_id", "")).strip()
    if explicit:
        return safe_filename(explicit)[:40]
    seed = "|".join(str(state.get(k, "")) for k in ("name", "world", "background"))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def affiliation_text_for(state):
    """Shared by visual_state (portrait regeneration trigger) and
    portrait_prompt (the actual prompt) so a change here is guaranteed to
    both describe AND actually redraw the portrait — an affiliation join
    that isn't part of the regeneration signature would silently never
    reach the art even with a correct prompt."""
    affiliations = state.get("affiliations", [])
    def _one(a):
        if isinstance(a, dict):
            faction = str(a.get("faction") or a.get("name") or "").strip()
            rank = str(a.get("rank") or "").strip()
            status = str(a.get("status") or "").strip()
            text = " — ".join(p for p in (faction, rank) if p)
            return f"{text} ({status})" if text and status and status.lower() != "active" else text
        return ai_text(a)
    text = "; ".join(t for t in (_one(a) for a in affiliations) if t) if isinstance(affiliations, list) else ""
    return text or "none recorded"


def visual_state(state):
    special = state.get("special", {}) if isinstance(state.get("special"), dict) else {}
    visual_special = {k: v for k, v in special.items() if VISUAL_SPECIAL_KEYS.search(str(k))}
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    return {
        "world": state.get("world", "Custom World"),
        "age": state.get("age", ""),
        "appearance": state.get("appearance_desc", ""),
        "traits": state.get("portrait_traits", []),
        "equipment": state.get("equipment", {}),
        "affiliations": affiliation_text_for(state),
        "origin": special.get("Origin", ""),
        "archetype": special.get("Archetype", ""),
        "position": state.get("position", ""),
        "visual_special": visual_special,
        "canonical_identity": identity.get("canonical_description", ""),
        "temporary_traits": identity.get("temporary_traits", []),
    }


def portrait_signature(state):
    raw = json.dumps(visual_state(state), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def derived_appearance(state):
    appearance = str(state.get("appearance_desc", "")).strip()
    if appearance:
        return appearance
    special = state.get("special", {}) if isinstance(state.get("special"), dict) else {}
    origin = special.get("Origin") or "local traveler"
    archetype = special.get("Archetype") or "adventurer"
    age = state.get("age") or "young adult"
    return (
        f"A {age} {origin} beginning as a {archetype}. Invent a coherent original face, hair, body type, "
        "and practical clothing that fit those traits and the setting; preserve them in later edits."
    )


def portrait_prompt(state, preserve_identity=False):
    world = state.get("world", "Custom World")
    style = WORLD_PORTRAIT_STYLES.get(world, WORLD_PORTRAIT_STYLES["Custom World"])
    backdrop = WORLD_BACKDROPS.get(world, WORLD_BACKDROPS["Custom World"])
    traits = "; ".join(ai_text(x) for x in state.get("portrait_traits", []) if ai_text(x)) or "none recorded"
    equipment = state.get("equipment", {})
    if isinstance(equipment, dict):
        equipment_text = "; ".join(f"{k}: {v}" for k, v in equipment.items()) or "ordinary setting-appropriate clothing"
    else:
        equipment_text = str(equipment) or "ordinary setting-appropriate clothing"
    affiliations_text = affiliation_text_for(state)
    special = visual_state(state)["visual_special"]
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    canonical = identity.get("canonical_description") or derived_appearance(state)
    temporary = "; ".join(str(x) for x in identity.get("temporary_traits", [])) or "none"
    identity_rule = (
        "Use the supplied previous portrait as the same person. Preserve facial identity, apparent age, body type, "
        "skin tone, and all unchanged features; edit only what the current description requires."
        if preserve_identity else
        "Create one consistent, memorable original player character identity from the description."
    )
    return f"""Create a polished square RPG character portrait.
WORLD: {world}
CHARACTER: {state.get('name') or 'Traveler'}
CANONICAL IDENTITY / APPEARANCE: {canonical}
ADDITIONAL VISIBLE TRAITS: {traits}
TEMPORARY VISIBLE CHANGES: {temporary}
CURRENT CLOTHING / EQUIPMENT: {equipment_text}
AFFILIATIONS / FACTIONS: {affiliations_text}
VISIBLE WORLD-SYSTEM TRAITS: {json.dumps(special, ensure_ascii=False, default=str)}
POSITION / ROLE: {state.get('position') or 'new adventurer'}

IDENTITY: {identity_rule}
STYLE: {style}. Capture the setting's broad visual language without copying any named artist, panel, cover, canon character, costume, pose, or emblem.
AFFILIATION MARKERS: If AFFILIATIONS / FACTIONS lists an active membership in a known in-world faction/order/village, dress the character with that group's ordinary everyday visual identifiers, fitting their actual rank/role — e.g. a shinobi affiliated with a hidden village wears a forehead-protector-style headband, an Akatsuki-type organization's member wears its signature dark cloak, a knight order's member wears its house colors or sigil-bearing surcoat. Render these as generic in-fiction garments/props appropriate to the affiliation (a plain metal-plate headband, a cloud-patterned cloak) rather than reproducing any franchise's exact official logo or insignia design.
COMPOSITION: one character only, waist-up, centered three-quarter view, face unobstructed, safe margins, made for a compact game portrait card.
BACKDROP: {backdrop}; atmospheric and subdued so the character dominates.
CONSTRAINTS: no text, captions, logo, watermark, border, UI, split panel, extra person, canon character likeness, or franchise emblem. Reflect every major physical, clothing, equipment, and transformation detail that is currently recorded."""


def fallback_url(state):
    slug = world_slug(state.get("world", "Custom World"))
    for candidate in (slug, "Custom_World"):
        for extension in ("webp", "png"):
            p = ASSET_ROOT / "generated_portraits" / f"{candidate}.{extension}"
            if p.exists():
                return f"/assets/generated_portraits/{candidate}.{extension}"
    return None


def cached_path(state):
    p = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    return p if p.exists() else None


def latest_path(state):
    candidates = [p for p in PORTRAIT_CACHE_DIR.glob(f"{campaign_portrait_id(state)}-*.*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def reference_path(state):
    identity = state.get("portrait_identity", {}) if isinstance(state.get("portrait_identity"), dict) else {}
    name = Path(str(identity.get("reference_file", ""))).name
    if not name:
        return None
    path = PORTRAIT_CACHE_DIR / name
    return path if path.exists() else None


def portrait_ready(settings):
    if not settings.get("portrait_generation_enabled", True):
        return False
    if settings.get("provider", "local") == "cloud":
        return bool(settings.get("api_key") and settings.get("image_model", "gpt-image-2"))
    return bool(settings.get("local_image_model"))


def portrait_view(state, settings):
    signature = portrait_signature(state)
    cached = cached_path(state)
    reference = reference_path(state)
    return {
        "_portrait_signature": signature,
        "_portrait_image": f"/portrait-cache/{cached.name}" if cached else f"/portrait-cache/{reference.name}" if reference else fallback_url(state),
        "_portrait_generated": bool(cached),
        "_portrait_reference": bool(reference and not cached),
        "_portrait_generation_enabled": bool(settings.get("portrait_generation_enabled", True)),
        "_portrait_generation_ready": portrait_ready(settings),
    }


def _request_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _multipart(fields, image_path):
    boundary = "----Worldwalker" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    suffix = image_path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image[]"; filename="portrait{suffix or ".png"}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(), image_path.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return boundary, b"".join(chunks)


def _decode_image(data):
    items = data.get("data", [])
    if not items:
        raise RuntimeError("The image server returned no portrait.")
    item = items[0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"], validate=True)
    elif item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=120) as response:
            raw = response.read()
    else:
        raise RuntimeError("The image server response did not contain image data.")
    if len(raw) < 1000 or len(raw) > 40 * 1024 * 1024:
        raise RuntimeError("The image server returned an invalid portrait file.")
    return raw


def generate_portrait(state, settings, force=False):
    if not settings.get("portrait_generation_enabled", True):
        raise RuntimeError("Automatic AI portraits are disabled in Settings.")
    provider = settings.get("provider", "local")
    if provider == "cloud":
        key = settings.get("api_key", "")
        if not key:
            raise RuntimeError("OpenAI Cloud portrait generation needs an API key in Settings.")
        base_url = "https://api.openai.com/v1"
        token = key
        model = settings.get("image_model") or "gpt-image-2"
    else:
        base_url = str(settings.get("local_base_url") or "http://localhost:1234/v1").rstrip("/")
        token = settings.get("local_token", "")
        model = str(settings.get("local_image_model") or "").strip()
        if not model:
            raise RuntimeError("Set a Local Image Model in Settings, or use the included world portrait.")

    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    if target.exists() and not force:
        return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "cached": True}

    previous = latest_path(state)
    quality = settings.get("portrait_quality", "low")
    if quality not in ("low", "medium", "high", "auto"):
        quality = "low"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        if previous and previous.exists():
            fields = {"model": model, "prompt": portrait_prompt(state, True), "size": "1024x1024", "quality": quality}
            boundary, body = _multipart(fields, previous)
            edit_headers = {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
            req = urllib.request.Request(base_url + "/images/edits", data=body, headers=edit_headers, method="POST")
            with urllib.request.urlopen(req, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        else:
            body = {"model": model, "prompt": portrait_prompt(state, False), "size": "1024x1024", "quality": quality}
            data = _request_json(base_url + "/images/generations", body, {**headers, "Content-Type": "application/json"})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Portrait generation HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not contact the configured image server: " + str(exc.reason)) from None

    raw = _decode_image(data)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)
    _record_portrait_usage(provider, quality)
    return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "cached": False}


def save_reference(state, raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 1000 or len(raw) > 12 * 1024 * 1024:
        raise ValueError("Reference portrait must be an image smaller than 12 MB.")
    if raw.startswith(b"\x89PNG"):
        ext = ".png"
    elif raw.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise ValueError("Reference portrait must be PNG, JPEG, or WebP.")
    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-reference{ext}"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, target)
    identity = state.setdefault("portrait_identity", {})
    identity["reference_file"] = target.name
    return {"image_url": f"/portrait-cache/{target.name}", "filename": target.name}


def portrait_history(state):
    prefix = campaign_portrait_id(state) + "-"
    items = []
    for p in sorted(PORTRAIT_CACHE_DIR.glob(prefix + "*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            items.append({"image_url": f"/portrait-cache/{p.name}", "filename": p.name,
                          "saved_at": int(p.stat().st_mtime), "reference": "-reference" in p.stem})
    return items[:20]


def revert_portrait(state):
    history = portrait_history(state)
    current = cached_path(state)
    candidates = [item for item in history if not current or item["filename"] != current.name]
    if not candidates:
        raise FileNotFoundError("No previous portrait exists for this campaign.")
    source = PORTRAIT_CACHE_DIR / candidates[0]["filename"]
    target = PORTRAIT_CACHE_DIR / f"{campaign_portrait_id(state)}-{portrait_signature(state)}.png"
    shutil.copyfile(source, target)
    return {"image_url": f"/portrait-cache/{target.name}", "signature": portrait_signature(state), "reverted_from": source.name}
