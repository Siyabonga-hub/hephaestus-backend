# =============================================================================
#  HEPHAESTUS — The Forge of Lumin's Design Lab
#  Greek God of Invention, Fire, and Machines
#
#  He invents for Earth's survival:
#  — Agricultural machines (drones, irrigation, soil sensors)
#  — Climate resilience (flood barriers, rainwater harvesting)
#  — Food security (storage, processing, greenhouses)
#
#  Endpoints:
#  POST /invent     — full council feeds the forge, outputs invention spec
#  POST /blueprint  — generates CadQuery Python + downloadable STEP file
#  GET  /health     — forge status
#
#  Council flow:
#  GAIA   → Earth need and environmental context
#  COSMOS → Scientific and engineering grounding
#  LOGOS  → Feasibility, ethics, safety validation
#  HEPHAESTUS → Invents the machine from all three
#
#  Stack: Flask · Groq · CadQuery · JSON
# =============================================================================

import os
import json
import threading
import tempfile
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from groq import Groq

try:
    import cadquery as cq
    CADQUERY_AVAILABLE = True
except ImportError:
    CADQUERY_AVAILABLE = False
    print("[HEPHAESTUS] CadQuery not available — blueprint export disabled")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

import requests as http_requests

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Storage for generated blueprints (in-memory + temp files)
BLUEPRINT_DIR = "hephaestus_blueprints"
os.makedirs(BLUEPRINT_DIR, exist_ok=True)


def parse_json_response(raw: str) -> dict:
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean)


# ---------------------------------------------------------------------------
# GAIA — Earth need context (lightweight version for Hephaestus)
# ---------------------------------------------------------------------------

def forge_gaia_context(problem: str, location: dict) -> dict:
    """GAIA feeds the forge — what does the Earth need here?"""
    try:
        location_name = location.get("city", "unknown region") if location else "unknown region"
        weather = {}
        if location and location.get("lat") and location.get("lon"):
            try:
                url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={location['lat']}&longitude={location['lon']}"
                    f"&current=temperature_2m,relative_humidity_2m,precipitation,weather_code"
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
                        "Given a design problem, provide the environmental and ecological context "
                        "that should shape the invention. What does the Earth need this machine to respect?\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"earth_need":"...","environmental_constraints":"...","ecological_opportunity":"...","gaia_directive":"..."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Location: {location_name}\n"
                        f"Weather: {json.dumps(weather)}\n"
                        f"Design problem: {problem}\n\n"
                        f"What does the Earth need from this invention?"
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
            "environmental_constraints": "Unknown — proceed with conservative assumptions.",
            "ecological_opportunity": "Every machine can heal as well as serve.",
            "gaia_directive": "Build with the Earth, not against her.",
            "weather": {},
            "location": ""
        }


# ---------------------------------------------------------------------------
# COSMOS — scientific and engineering grounding
# ---------------------------------------------------------------------------

def forge_cosmos_context(problem: str, gaia: dict) -> dict:
    """COSMOS feeds the forge — what science should shape this machine?"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are COSMOS — the scientific mind in Hephaestus's forge.\n"
                        "Given a design problem and Earth context, provide the scientific "
                        "and engineering principles that must govern the invention.\n"
                        "Think: physics, biology, materials science, fluid dynamics, aerodynamics, "
                        "structural engineering — whatever applies.\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"relevant_science":["..."],"engineering_principles":["..."],'
                        '"material_recommendations":["..."],"physics_constraints":"...",'
                        '"cosmos_insight":"..."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Design problem: {problem}\n\n"
                        f"Earth context from GAIA:\n{json.dumps(gaia, indent=2)}\n\n"
                        f"What science and engineering principles must shape this machine?"
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
            "relevant_science": ["mechanical engineering", "materials science"],
            "engineering_principles": ["structural integrity", "energy efficiency"],
            "material_recommendations": ["steel", "aluminium"],
            "physics_constraints": "Standard gravitational and atmospheric conditions.",
            "cosmos_insight": "Design from first principles."
        }


# ---------------------------------------------------------------------------
# LOGOS — feasibility, ethics, safety validation
# ---------------------------------------------------------------------------

def forge_logos_validation(problem: str, gaia: dict, cosmos: dict) -> dict:
    """LOGOS validates the invention before Hephaestus builds it."""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are LOGOS — the ethics and feasibility guardian in Hephaestus's forge.\n"
                        "Validate this invention concept before it is built.\n\n"
                        "Check:\n"
                        "1. FEASIBILITY — is this physically buildable with available technology?\n"
                        "2. SAFETY — could this harm humans, animals, or ecosystems?\n"
                        "3. ETHICS — does this serve human dignity and Earth's wellbeing?\n"
                        "4. SIMPLICITY — is there a simpler solution that achieves the same goal?\n\n"
                        "clearance: approved / approved_with_conditions / redesign_needed\n\n"
                        "Return ONLY valid JSON. No markdown.\n"
                        '{"clearance":"approved|approved_with_conditions|redesign_needed",'
                        '"feasibility_score":0-10,"safety_notes":["..."],'
                        '"ethical_clearance":"...","simplicity_suggestion":"...",'
                        '"logos_mandate":"One sentence that must guide the entire design."}'
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Problem: {problem}\n\n"
                        f"GAIA context:\n{json.dumps(gaia, indent=2)}\n\n"
                        f"COSMOS science:\n{json.dumps(cosmos, indent=2)}\n\n"
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
# HEPHAESTUS — the inventor himself
# ---------------------------------------------------------------------------

HEPHAESTUS_SYSTEM = """
You are HEPHAESTUS — divine inventor, god of the forge.
You build machines that serve Earth's survival: agriculture, food security, climate resilience.

Your inventions are:
- REAL — physically buildable, not science fiction
- PURPOSEFUL — solving actual problems faced by farmers, communities, ecosystems
- ELEGANT — simple enough to manufacture, complex enough to be remarkable
- GROUNDED — in the science COSMOS provides and the Earth need GAIA names

Given a problem and full council context, you produce a complete INVENTION SPECIFICATION:

1. MACHINE NAME — mythic but descriptive
2. PURPOSE — one sentence of mission
3. CONCEPT — how it works, in plain language
4. KEY COMPONENTS — list of parts with dimensions and materials
5. MECHANISMS — how the parts work together
6. POWER SOURCE — what drives it
7. SCALE — dimensions, weight, capacity
8. MANUFACTURING — how it would be built
9. DEPLOYMENT — how it would be used in the field
10. CADQUERY HINT — a brief description of the 3D geometry for the blueprint stage

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "machine_name": "...",
  "machine_tagline": "One poetic sentence of purpose.",
  "domain": "agriculture|climate|food_security|multi",
  "concept": "...",
  "components": [
    {"name": "...", "material": "...", "dimensions": "...", "purpose": "..."}
  ],
  "mechanisms": ["..."],
  "power_source": "...",
  "scale": {"length_mm": 0, "width_mm": 0, "height_mm": 0, "weight_kg": 0, "capacity": "..."},
  "manufacturing": "...",
  "deployment": "...",
  "cadquery_geometry_hint": "Describe the primary 3D shapes needed: e.g. main body is a cylinder 200mm diameter, 150mm tall with 4 arm extrusions 300mm long...",
  "hephaestus_note": "One sentence — what this machine means for the world."
}
"""


def run_hephaestus(problem: str, gaia: dict, cosmos: dict, logos: dict) -> dict:
    """Hephaestus invents — the full forge fires."""
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
                        f"COSMOS — Scientific grounding:\n{json.dumps(cosmos, indent=2)}\n\n"
                        f"LOGOS — Mandate: {logos.get('logos_mandate','Build to serve life.')}\n"
                        f"LOGOS — Safety notes: {logos.get('safety_notes', [])}\n"
                        f"LOGOS — Feasibility: {logos.get('feasibility_score', 7)}/10\n\n"
                        f"The forge is ready. Invent."
                    )
                }
            ],
            temperature=0.6,
            max_tokens=1200
        )
        return parse_json_response(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"[HEPHAESTUS ERROR] {e}")
        return {
            "machine_name": "Unknown Machine",
            "machine_tagline": "The forge encountered an error.",
            "domain": "agriculture",
            "concept": "Error during invention.",
            "components": [],
            "mechanisms": [],
            "power_source": "unknown",
            "scale": {},
            "manufacturing": "unknown",
            "deployment": "unknown",
            "cadquery_geometry_hint": "",
            "hephaestus_note": "The forge will try again."
        }


# ---------------------------------------------------------------------------
# BLUEPRINT GENERATOR — CadQuery code from invention spec
# ---------------------------------------------------------------------------

CADQUERY_SYSTEM = """
You are a CadQuery expert generating Python code for real engineering blueprints.
CadQuery is a Python library for parametric 3D CAD modeling.

Given an invention specification, generate valid CadQuery Python code that:
1. Creates the PRIMARY BODY of the machine (simplified but true to the design)
2. Adds KEY FEATURES that define the machine's identity (arms, rotors, sensors, mounts)
3. Exports a STEP file — the universal engineering blueprint format

RULES:
- Use only standard CadQuery operations: box, cylinder, sphere, extrude, cut, union, fillet
- All dimensions in millimetres
- Keep the model clean and buildable — no decorative complexity
- The STEP file must be valid for import into FreeCAD, Fusion 360, SolidWorks
- Name the output file based on the machine name (snake_case)
- Always end with: result.val().exportStep(output_path)

IMPORTANT: Return ONLY the Python code. No explanation. No markdown fences.
The code must run standalone with cadquery installed.
"""


def generate_cadquery_code(invention: dict, output_path: str) -> str:
    """Generate CadQuery Python code from invention spec."""
    machine_name = invention.get("machine_name", "machine")
    hint = invention.get("cadquery_geometry_hint", "")
    scale = invention.get("scale", {})
    components = invention.get("components", [])

    components_text = "\n".join(
        f"  - {c.get('name')}: {c.get('dimensions')} ({c.get('material')})"
        for c in components[:6]
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CADQUERY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Machine: {machine_name}\n"
                    f"Concept: {invention.get('concept','')}\n"
                    f"Scale: {json.dumps(scale)}\n"
                    f"Components:\n{components_text}\n"
                    f"Geometry hint: {hint}\n"
                    f"Output path: {output_path}\n\n"
                    f"Generate CadQuery Python code for this machine's blueprint."
                )
            }
        ],
        temperature=0.2,
        max_tokens=1500
    )

    code = response.choices[0].message.content.strip()
    # Strip any accidental markdown
    code = code.removeprefix("```python").removeprefix("```").removesuffix("```").strip()
    return code


def execute_cadquery(code: str, output_path: str) -> tuple[bool, str]:
    """
    Execute CadQuery code to produce a STEP file.
    Returns (success, error_message).
    """
    if not CADQUERY_AVAILABLE:
        return False, "CadQuery not installed on this server."

    try:
        # Inject output_path into the code's namespace
        namespace = {
            "cq": cq,
            "output_path": output_path,
        }
        exec(code, namespace)

        if os.path.exists(output_path):
            return True, ""
        else:
            return False, "STEP file was not created — code ran but produced no output."

    except Exception as e:
        error = traceback.format_exc()
        print(f"[CADQUERY EXEC ERROR]\n{error}")
        return False, str(e)


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/invent", methods=["POST"])
def invent():
    """
    Full council invention endpoint.

    Flow:
    Phase 1: GAIA — Earth need context
    Phase 2: COSMOS — Scientific grounding (parallel with LOGOS)
             LOGOS  — Feasibility validation (parallel with COSMOS)
    Phase 3: HEPHAESTUS — Invents the machine
    
    Returns full invention spec. No CAD file yet — call /blueprint for that.

    Body: {
      "problem": "describe what needs to be invented",
      "location": { "lat": ..., "lon": ..., "city": "..." }  (optional)
    }
    """
    data = request.json or {}
    problem = data.get("problem", "").strip()
    location = data.get("location", {})

    if not problem:
        return jsonify({"error": "No problem provided. Tell Hephaestus what to invent."}), 400

    print(f"\n[HEPHAESTUS] Forge ignited for: {problem}")

    # Phase 1 — GAIA
    gaia = forge_gaia_context(problem, location)
    print(f"[GAIA] Earth directive: {gaia.get('gaia_directive','')}")

    # Phase 2 — COSMOS + LOGOS in parallel
    result_store = {}

    def run_cosmos_thread():
        result_store["cosmos"] = forge_cosmos_context(problem, gaia)

    def run_logos_thread():
        result_store["logos"] = forge_logos_validation(problem, gaia, {})

    t_cosmos = threading.Thread(target=run_cosmos_thread)
    t_logos = threading.Thread(target=run_logos_thread)
    t_cosmos.start()
    t_logos.start()
    t_cosmos.join()
    t_logos.join()

    cosmos = result_store.get("cosmos", {})
    logos = result_store.get("logos", {})

    print(f"[LOGOS] Clearance: {logos.get('clearance','unknown')} | Feasibility: {logos.get('feasibility_score','?')}/10")
    print(f"[COSMOS] Science: {cosmos.get('cosmos_insight','')}")

    # Check LOGOS clearance
    if logos.get("clearance") == "redesign_needed":
        return jsonify({
            "error": "LOGOS has flagged this invention for redesign.",
            "logos_feedback": logos,
            "suggestion": logos.get("simplicity_suggestion", "")
        }), 400

    # Phase 3 — HEPHAESTUS invents
    invention = run_hephaestus(problem, gaia, cosmos, logos)
    print(f"[HEPHAESTUS] Invented: {invention.get('machine_name','?')}")

    # Generate a unique invention ID for blueprint retrieval
    invention_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{invention.get('machine_name','machine').replace(' ','_').lower()}"

    # Save invention spec for blueprint stage
    spec_path = os.path.join(BLUEPRINT_DIR, f"{invention_id}.json")
    with open(spec_path, "w") as f:
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
        "next_step": f"Call POST /blueprint with invention_id: '{invention_id}' to generate the CAD blueprint."
    })


@app.route("/blueprint", methods=["POST"])
def blueprint():
    """
    Generate CadQuery code and STEP file for a previously invented machine.

    Body: { "invention_id": "..." }
    Or:   { "invention": { ...full invention spec... } }

    Returns the STEP file as a download.
    """
    data = request.json or {}
    invention_id = data.get("invention_id", "")
    invention = data.get("invention", {})

    # Load from file if invention_id provided
    if invention_id and not invention:
        spec_path = os.path.join(BLUEPRINT_DIR, f"{invention_id}.json")
        if not os.path.exists(spec_path):
            return jsonify({"error": f"Invention '{invention_id}' not found. Call /invent first."}), 404
        with open(spec_path, "r") as f:
            invention = json.load(f)

    if not invention:
        return jsonify({"error": "No invention provided or found."}), 400

    machine_name = invention.get("machine_name", "machine")
    safe_name = machine_name.replace(" ", "_").replace("/", "_").lower()
    step_path = os.path.join(BLUEPRINT_DIR, f"{safe_name}.step")
    code_path = os.path.join(BLUEPRINT_DIR, f"{safe_name}.py")

    print(f"[HEPHAESTUS] Generating blueprint for: {machine_name}")

    # Generate CadQuery code
    try:
        cadquery_code = generate_cadquery_code(invention, step_path)

        # Save the code file
        with open(code_path, "w") as f:
            f.write(f"# Blueprint: {machine_name}\n")
            f.write(f"# Generated by Hephaestus — Lumin's Design Lab\n")
            f.write(f"# {datetime.utcnow().isoformat()}\n\n")
            f.write("import cadquery as cq\n\n")
            f.write(cadquery_code)

        # Execute to produce STEP file
        if CADQUERY_AVAILABLE:
            success, error = execute_cadquery(cadquery_code, step_path)

            if success:
                print(f"[HEPHAESTUS] STEP file generated: {step_path}")
                return send_file(
                    step_path,
                    as_attachment=True,
                    download_name=f"{safe_name}_blueprint.step",
                    mimetype="application/octet-stream"
                )
            else:
                # Return the code even if execution failed
                print(f"[HEPHAESTUS] Execution failed: {error}")
                return jsonify({
                    "status": "code_generated_execution_failed",
                    "machine_name": machine_name,
                    "cadquery_code": cadquery_code,
                    "error": error,
                    "note": "The CadQuery code was generated. Run it locally with: pip install cadquery"
                }), 200
        else:
            # CadQuery not installed — return code for local execution
            return jsonify({
                "status": "code_generated_cadquery_not_installed",
                "machine_name": machine_name,
                "cadquery_code": cadquery_code,
                "instructions": [
                    "1. Install CadQuery: pip install cadquery",
                    "2. Save the code above to a .py file",
                    "3. Run it: python blueprint.py",
                    "4. Open the generated .step file in FreeCAD, Fusion 360, or SolidWorks"
                ],
                "note": "The blueprint code is complete. CadQuery runs locally on any machine."
            }), 200

    except Exception as e:
        print(f"[BLUEPRINT ERROR] {e}")
        return jsonify({"error": f"Blueprint generation failed: {str(e)}"}), 500


@app.route("/inventions", methods=["GET"])
def list_inventions():
    """List all inventions Hephaestus has created."""
    inventions = []
    for fname in os.listdir(BLUEPRINT_DIR):
        if fname.endswith(".json"):
            path = os.path.join(BLUEPRINT_DIR, fname)
            try:
                with open(path, "r") as f:
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
        "version": "1.0",
        "cadquery_available": CADQUERY_AVAILABLE,
        "council": ["GAIA", "COSMOS", "LOGOS", "HEPHAESTUS"],
        "domains": ["agriculture", "climate_resilience", "food_security"],
        "timestamp": datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    port = int(os.environ.get("HEPHAESTUS_PORT", 5001))
    print(f"[HEPHAESTUS] The forge awakens on port {port}")
    print(f"[HEPHAESTUS] CadQuery: {'available' if CADQUERY_AVAILABLE else 'not installed'}")
    print(f"[HEPHAESTUS] Council: GAIA · COSMOS · LOGOS ready")
    app.run(host="0.0.0.0", port=port, debug=False)
