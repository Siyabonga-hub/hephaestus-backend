# =============================================================================
#  HEPHAESTUS — The Forge of Lumin's Design Lab v2.0
#  Now with Zoo.dev Text-to-CAD API — real STEP files, no local install
#
#  Council flow:
#  GAIA   → Earth need and environmental context
#  COSMOS → Scientific and engineering grounding
#  LOGOS  → Feasibility, ethics, safety validation
#  HEPHAESTUS → Invents the machine
#  ZOO.DEV → Turns invention into a real downloadable STEP blueprint
#
#  Endpoints:
#  POST /invent     → full council invents, returns spec
#  POST /blueprint  → Zoo.dev generates STEP file, returns download
#  GET  /inventions → list all inventions
#  GET  /health     → forge status
# =============================================================================

import os
import json
import time
import base64
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from groq import Groq
import requests as http_requests

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
ZOO_API_KEY = os.environ.get("ZOO_API_KEY", "")
ZOO_BASE_URL = "https://api.zoo.dev"

BLUEPRINT_DIR = "hephaestus_blueprints"
os.makedirs(BLUEPRINT_DIR, exist_ok=True)


def parse_json_response(raw: str) -> dict:
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean)


# ---------------------------------------------------------------------------
# ZOO.DEV — Text-to-CAD API integration
# ---------------------------------------------------------------------------

def build_zoo_prompt(invention: dict) -> str:
    """
    Convert Hephaestus's invention spec into a precise Zoo.dev prompt.
    Zoo.dev works best with explicit geometric descriptions.
    """
    name = invention.get("machine_name", "machine")
    hint = invention.get("cadquery_geometry_hint", "")
    scale = invention.get("scale", {})
    components = invention.get("components", [])

    # Build component descriptions
    component_lines = []
    for c in components[:5]:  # Zoo.dev works better with fewer, clearer parts
        dim = c.get("dimensions", "")
        mat = c.get("material", "")
        cname = c.get("name", "")
        component_lines.append(f"{cname}: {dim}, made of {mat}")

    components_text = ". ".join(component_lines)

    # Build the geometric prompt — explicit dimensions are key for Zoo.dev
    prompt = (
        f"{name} — {invention.get('machine_tagline', '')}. "
        f"Primary geometry: {hint}. "
        f"Overall dimensions: {scale.get('length_mm', 200)}mm long, "
        f"{scale.get('width_mm', 100)}mm wide, "
        f"{scale.get('height_mm', 100)}mm tall. "
        f"Key components: {components_text}. "
        f"Design purpose: {invention.get('concept', '')}."
    )

    return prompt


def generate_step_from_zoo(zoo_prompt: str, machine_name: str) -> tuple[bool, str, str]:
    """
    Call Zoo.dev Text-to-CAD API and return a STEP file.

    Returns: (success, step_file_path_or_error, operation_id)

    Zoo.dev flow:
    1. POST /ml/text-to-cad/{format} → async operation starts, returns id
    2. Poll GET /async/operations/{id} until completed
    3. Extract STEP file from outputs
    """
    if not ZOO_API_KEY:
        return False, "ZOO_API_KEY not set in environment variables.", ""

    headers = {
        "Authorization": f"Bearer {ZOO_API_KEY}",
        "Content-Type": "application/json"
    }

    # Step 1 — Submit text-to-CAD request
    try:
        response = http_requests.post(
            f"{ZOO_BASE_URL}/ml/text-to-cad/step",
            headers=headers,
            json={"prompt": zoo_prompt},
            timeout=30
        )

        if response.status_code not in [200, 201, 202]:
            return False, f"Zoo.dev API error {response.status_code}: {response.text}", ""

        data = response.json()
        operation_id = data.get("id", "")

        if not operation_id:
            # Sometimes Zoo.dev returns the result immediately (cache hit)
            if data.get("status") == "completed" and data.get("outputs"):
                return extract_step_file(data, machine_name)
            return False, "No operation ID returned from Zoo.dev.", ""

        print(f"[ZOO.DEV] Operation started: {operation_id}")

    except Exception as e:
        return False, f"Zoo.dev request failed: {str(e)}", ""

    # Step 2 — Poll for completion
    max_polls = 30  # Max 5 minutes (10s intervals)
    poll_interval = 10

    for poll in range(max_polls):
        time.sleep(poll_interval)

        try:
            poll_response = http_requests.get(
                f"{ZOO_BASE_URL}/async/operations/{operation_id}",
                headers=headers,
                timeout=15
            )

            if poll_response.status_code != 200:
                print(f"[ZOO.DEV] Poll error: {poll_response.status_code}")
                continue

            result = poll_response.json()
            status = result.get("status", "")
            print(f"[ZOO.DEV] Poll {poll + 1}/{max_polls}: {status}")

            if status == "completed":
                return extract_step_file(result, machine_name)

            elif status == "failed":
                error = result.get("error", "Unknown error from Zoo.dev")
                return False, f"Zoo.dev generation failed: {error}", operation_id

            # Still running — continue polling

        except Exception as e:
            print(f"[ZOO.DEV] Poll exception: {e}")
            continue

    return False, "Zoo.dev timed out after 5 minutes.", operation_id


def extract_step_file(result: dict, machine_name: str) -> tuple[bool, str, str]:
    """Extract and save STEP file from Zoo.dev response."""
    try:
        outputs = result.get("outputs", {})

        if not outputs:
            return False, "Zoo.dev returned no output files.", result.get("id", "")

        # Find the STEP file — Zoo.dev returns it as "source.step"
        step_data = None
        for key, value in outputs.items():
            if "step" in key.lower() or key == "source.step":
                step_data = value
                break

        if step_data is None:
            # Try first output
            step_data = list(outputs.values())[0]

        # Decode — Zoo.dev returns base64 encoded content
        if isinstance(step_data, str):
            try:
                decoded = base64.b64decode(step_data)
            except Exception:
                decoded = step_data.encode("utf-8")
        elif isinstance(step_data, bytes):
            decoded = step_data
        else:
            return False, "Unexpected STEP data format from Zoo.dev.", ""

        # Save to file
        safe_name = machine_name.replace(" ", "_").replace("/", "_").lower()
        step_path = os.path.join(BLUEPRINT_DIR, f"{safe_name}.step")

        with open(step_path, "wb") as f:
            f.write(decoded)

        print(f"[ZOO.DEV] STEP file saved: {step_path} ({len(decoded)} bytes)")
        return True, step_path, result.get("id", "")

    except Exception as e:
        return False, f"Failed to extract STEP file: {str(e)}", ""


# ---------------------------------------------------------------------------
# GAIA — Earth need context
# ---------------------------------------------------------------------------

def forge_gaia_context(problem: str, location: dict) -> dict:
    try:
        location_name = location.get("city", "unknown region") if location else "unknown region"
        weather = {}
        if location and location.get("lat") and location.get("lon"):
            try:
                url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={location['lat']}&longitude={location['lon']}"
                    f"&current=temperature_2m,relative_humidity_2m,precipitation"
                    f"&timezone=auto"
                )
                data = http_requests.get(url, timeout=4).json()
                current = data.get("current", {})
                weather = {
                    "temperature_c": current.get("temperature_2m"),
                    "humidity_pct": current.get("relative_humidity_2m"),
                    "precipitation_mm": current.get("precipitation"),
                }
            except Exception:
                pass

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are GAIA — Earth's voice in Hephaestus's forge.\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"earth_need":"...","environmental_constraints":"...",'
                        '"ecological_opportunity":"...","gaia_directive":"..."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Location: {location_name}\nWeather: {json.dumps(weather)}\n"
                        f"Design problem: {problem}\nWhat does the Earth need from this invention?"
                    )
                }
            ],
            temperature=0.4,
            max_tokens=300
        )
        result = parse_json_response(response.choices[0].message.content.strip())
        result["weather"] = weather
        result["location"] = location_name
        return result
    except Exception as e:
        print(f"[FORGE GAIA ERROR] {e}")
        return {
            "earth_need": "Design for resilience and minimal environmental impact.",
            "environmental_constraints": "Unknown — proceed conservatively.",
            "ecological_opportunity": "Every machine can heal as well as serve.",
            "gaia_directive": "Build with the Earth, not against her.",
            "weather": {}, "location": ""
        }


# ---------------------------------------------------------------------------
# COSMOS — scientific and engineering grounding
# ---------------------------------------------------------------------------

def forge_cosmos_context(problem: str, gaia: dict) -> dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are COSMOS — scientific mind in Hephaestus's forge.\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"relevant_science":["..."],"engineering_principles":["..."],'
                        '"material_recommendations":["..."],"physics_constraints":"...",'
                        '"cosmos_insight":"..."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Design problem: {problem}\n"
                        f"GAIA context: {json.dumps(gaia, indent=2)}\n"
                        f"What science and engineering must shape this machine?"
                    )
                }
            ],
            temperature=0.3,
            max_tokens=500
        )
        return parse_json_response(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"[FORGE COSMOS ERROR] {e}")
        return {
            "relevant_science": ["mechanical engineering"],
            "engineering_principles": ["structural integrity", "energy efficiency"],
            "material_recommendations": ["steel", "aluminium"],
            "physics_constraints": "Standard conditions.",
            "cosmos_insight": "Design from first principles."
        }


# ---------------------------------------------------------------------------
# LOGOS — feasibility, ethics, safety
# ---------------------------------------------------------------------------

def forge_logos_validation(problem: str, gaia: dict, cosmos: dict) -> dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are LOGOS — ethics and feasibility guardian in Hephaestus's forge.\n"
                        "clearance: approved / approved_with_conditions / redesign_needed\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"clearance":"...","feasibility_score":0-10,"safety_notes":["..."],'
                        '"ethical_clearance":"...","simplicity_suggestion":"...",'
                        '"logos_mandate":"..."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Problem: {problem}\n"
                        f"GAIA: {json.dumps(gaia, indent=2)}\n"
                        f"COSMOS: {json.dumps(cosmos, indent=2)}\n"
                        f"Validate this invention."
                    )
                }
            ],
            temperature=0.2,
            max_tokens=400
        )
        return parse_json_response(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"[FORGE LOGOS ERROR] {e}")
        return {
            "clearance": "approved",
            "feasibility_score": 7,
            "safety_notes": ["Standard engineering safety practices apply."],
            "ethical_clearance": "Serves Earth and human wellbeing.",
            "simplicity_suggestion": "None identified.",
            "logos_mandate": "Build to serve life, not to impress."
        }


# ---------------------------------------------------------------------------
# HEPHAESTUS — the inventor
# ---------------------------------------------------------------------------

HEPHAESTUS_SYSTEM = """
You are HEPHAESTUS — divine inventor, god of the forge.
You build machines that serve Earth's survival.

Your inventions are REAL — physically buildable, purposeful, elegant.

Produce a complete INVENTION SPECIFICATION.
For cadquery_geometry_hint: be VERY specific about 3D geometry.
Example: "Main body is a cylinder 300mm diameter 200mm tall. Four arms extend 400mm from center,
each 30mm square cross-section. Rotor mounts are cylinders 50mm diameter 20mm tall at arm ends."
This hint feeds directly into a CAD generator — precision matters.

Return ONLY valid JSON. No preamble. No markdown fences.
{
  "machine_name": "...",
  "machine_tagline": "...",
  "domain": "agriculture|climate|food_security|multi",
  "concept": "...",
  "components": [
    {"name": "...", "material": "...", "dimensions": "...", "purpose": "..."}
  ],
  "mechanisms": ["..."],
  "power_source": "...",
  "scale": {
    "length_mm": 0, "width_mm": 0, "height_mm": 0,
    "weight_kg": 0, "capacity": "..."
  },
  "manufacturing": "...",
  "deployment": "...",
  "cadquery_geometry_hint": "Precise geometric description for CAD generation...",
  "hephaestus_note": "..."
}
"""


def run_hephaestus(problem: str, gaia: dict, cosmos: dict, logos: dict) -> dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": HEPHAESTUS_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"INVENTION BRIEF: {problem}\n\n"
                        f"GAIA — Earth need:\n{json.dumps(gaia, indent=2)}\n\n"
                        f"COSMOS — Science:\n{json.dumps(cosmos, indent=2)}\n\n"
                        f"LOGOS mandate: {logos.get('logos_mandate','Build to serve life.')}\n"
                        f"LOGOS safety: {logos.get('safety_notes', [])}\n"
                        f"LOGOS feasibility: {logos.get('feasibility_score', 7)}/10\n\n"
                        f"The forge is ready. Invent."
                    )
                }
            ],
            temperature=0.6,
            max_tokens=1500
        )
        return parse_json_response(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"[HEPHAESTUS ERROR] {e}")
        return {
            "machine_name": "Unknown Machine",
            "machine_tagline": "The forge encountered an error.",
            "domain": "agriculture", "concept": "Error during invention.",
            "components": [], "mechanisms": [], "power_source": "unknown",
            "scale": {}, "manufacturing": "unknown", "deployment": "unknown",
            "cadquery_geometry_hint": "", "hephaestus_note": "The forge will try again."
        }


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/invent", methods=["POST"])
def invent():
    """
    Full council invention — GAIA → COSMOS+LOGOS → HEPHAESTUS.
    Returns invention spec. Call /blueprint next for the STEP file.

    Body: { "problem": "...", "location": { "lat", "lon", "city" } }
    """
    data = request.json or {}
    problem = data.get("problem", "").strip()
    location = data.get("location", {})

    if not problem:
        return jsonify({"error": "Tell Hephaestus what to invent."}), 400

    print(f"\n[HEPHAESTUS] Forge ignited: {problem}")

    # Phase 1 — GAIA
    gaia = forge_gaia_context(problem, location)

    # Phase 2 — COSMOS + LOGOS parallel
    result_store = {}

    def cosmos_thread():
        result_store["cosmos"] = forge_cosmos_context(problem, gaia)

    def logos_thread():
        result_store["logos"] = forge_logos_validation(problem, gaia, {})

    t1 = threading.Thread(target=cosmos_thread)
    t2 = threading.Thread(target=logos_thread)
    t1.start(); t2.start()
    t1.join(); t2.join()

    cosmos = result_store.get("cosmos", {})
    logos = result_store.get("logos", {})

    if logos.get("clearance") == "redesign_needed":
        return jsonify({
            "error": "LOGOS flagged this for redesign.",
            "logos_feedback": logos
        }), 400

    # Phase 3 — HEPHAESTUS
    invention = run_hephaestus(problem, gaia, cosmos, logos)
    print(f"[HEPHAESTUS] Invented: {invention.get('machine_name')}")

    # Save spec
    invention_id = (
        f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_"
        f"{invention.get('machine_name','machine').replace(' ','_').lower()}"
    )
    with open(os.path.join(BLUEPRINT_DIR, f"{invention_id}.json"), "w") as f:
        json.dump(invention, f, indent=2)

    return jsonify({
        "invention_id": invention_id,
        "invention": invention,
        "council": {
            "gaia_directive": gaia.get("gaia_directive"),
            "gaia_location": gaia.get("location"),
            "cosmos_insight": cosmos.get("cosmos_insight"),
            "logos_clearance": logos.get("clearance"),
            "logos_feasibility": logos.get("feasibility_score"),
            "logos_mandate": logos.get("logos_mandate"),
        },
        "next_step": f"POST /blueprint with invention_id: '{invention_id}'"
    })


@app.route("/blueprint", methods=["POST"])
def blueprint():
    """
    Generate a real STEP file via Zoo.dev Text-to-CAD API.
    Returns downloadable .step file.

    Body: { "invention_id": "..." }
    Note: Takes 1-3 minutes — Zoo.dev generates async.
    """
    data = request.json or {}
    invention_id = data.get("invention_id", "")

    if not invention_id:
        return jsonify({"error": "Provide an invention_id from /invent"}), 400

    spec_path = os.path.join(BLUEPRINT_DIR, f"{invention_id}.json")
    if not os.path.exists(spec_path):
        return jsonify({"error": f"Invention '{invention_id}' not found. Call /invent first."}), 404

    with open(spec_path, "r") as f:
        invention = json.load(f)

    machine_name = invention.get("machine_name", "machine")
    print(f"[HEPHAESTUS] Generating blueprint for: {machine_name}")

    # Build Zoo.dev prompt from invention spec
    zoo_prompt = build_zoo_prompt(invention)
    print(f"[ZOO.DEV] Prompt: {zoo_prompt[:100]}...")

    # Generate STEP file via Zoo.dev
    success, result, operation_id = generate_step_from_zoo(zoo_prompt, machine_name)

    if success:
        step_path = result
        safe_name = machine_name.replace(" ", "_").lower()
        return send_file(
            step_path,
            as_attachment=True,
            download_name=f"{safe_name}_blueprint.step",
            mimetype="application/octet-stream"
        )
    else:
        # Return the Zoo.dev prompt so user can try manually at text-to-cad.zoo.dev
        return jsonify({
            "status": "zoo_generation_failed",
            "machine_name": machine_name,
            "error": result,
            "zoo_prompt": zoo_prompt,
            "manual_fallback": (
                "Go to text-to-cad.zoo.dev, paste the zoo_prompt above, "
                "and download the STEP file manually."
            )
        }), 200


@app.route("/inventions", methods=["GET"])
def list_inventions():
    inventions = []
    for fname in os.listdir(BLUEPRINT_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(BLUEPRINT_DIR, fname), "r") as f:
                    spec = json.load(f)
                inventions.append({
                    "invention_id": fname.replace(".json", ""),
                    "machine_name": spec.get("machine_name", "Unknown"),
                    "machine_tagline": spec.get("machine_tagline", ""),
                    "domain": spec.get("domain", "unknown"),
                    "hephaestus_note": spec.get("hephaestus_note", "")
                })
            except Exception:
                continue
    inventions.sort(key=lambda x: x["invention_id"], reverse=True)
    return jsonify({"count": len(inventions), "inventions": inventions})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "forge": "HEPHAESTUS",
        "version": "2.0",
        "zoo_api_configured": bool(ZOO_API_KEY),
        "council": ["GAIA", "COSMOS", "LOGOS", "HEPHAESTUS"],
        "cad_provider": "Zoo.dev Text-to-CAD API",
        "output_format": "STEP (ISO 10303)",
        "timestamp": datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    port = int(os.environ.get("HEPHAESTUS_PORT", 5001))
    print(f"[HEPHAESTUS] Forge v2.0 awakening on port {port}")
    print(f"[HEPHAESTUS] Zoo.dev: {'configured' if ZOO_API_KEY else 'NOT SET — add ZOO_API_KEY'}")
    app.run(host="0.0.0.0", port=port, debug=False)
