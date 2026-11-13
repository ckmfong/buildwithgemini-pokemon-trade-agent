# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Dict, List, Optional
import time
from google.cloud import firestore
from google.cloud import storage
from google import genai

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.genai import types

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback


MODEL = "gemini-2.5-flash"
PROJECT_ID = "qwiklabs-gcp-04-e4af8e742d59"
BUCKET_NAME = "pokemon-trade-cards-qwiklabs-gcp-04-e4af8e742d59-media"
AGENT_ENGINE_ID = "projects/325443549905/locations/us-east1/reasoningEngines/8799812670044766208"
SANDBOX_ID = "projects/325443549905/locations/us-east1/reasoningEngines/8799812670044766208/sandboxEnvironments/3639854078915248128"


def _get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def _get_storage_client() -> storage.Client:
    return storage.Client(project=PROJECT_ID)


def list_pokemon_cards(max_results: int = 10) -> List[Dict[str, Any]]:
    """Lists Pokemon cards currently stored in the collection.

    Args:
        max_results: Maximum number of cards to return (default 10).

    Returns:
        A list of dictionaries representing Pokemon cards and their details.
    """
    db = _get_firestore_client()
    docs = db.collection("pokemon_cards").limit(max_results).stream()
    cards = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        cards.append(data)
    return cards


def search_pokemon_card(name: str) -> List[Dict[str, Any]]:
    """Searches for Pokemon cards in the catalog matching a name substring.

    Args:
        name: The name or partial name of the Pokemon card (e.g. 'Charizard', 'Pikachu').

    Returns:
        A list of matching Pokemon card records.
    """
    db = _get_firestore_client()
    docs = db.collection("pokemon_cards").stream()
    query_lower = name.lower()
    matches = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if query_lower in data.get("name", "").lower():
            matches.append(data)
    return matches


def add_or_update_pokemon_card(
    card_id: str,
    name: str,
    set_name: str,
    card_type: str,
    rarity: str,
    condition: str,
    estimated_value_usd: float,
    available_for_trade: bool = True,
    owner: str = "collector",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds a new Pokemon card or updates an existing card in the collection.

    Args:
        card_id: Unique identifier for the card (e.g., 'mewtwo-gx-promo').
        name: Name of the card (e.g. 'Mewtwo GX').
        set_name: Set or expansion (e.g. 'Hidden Fates').
        card_type: Pokemon element or card type (e.g. 'Psychic', 'Water').
        rarity: Rarity of the card (e.g. 'Ultra Rare', 'Secret Rare').
        condition: Card condition (e.g. 'Mint', 'Near Mint', 'Lightly Played').
        estimated_value_usd: Market value estimate in USD.
        available_for_trade: Whether this card is open for trade offers.
        owner: Owner tag, defaults to 'collector'.
        notes: Optional extra details, provenance, or notes.

    Returns:
        Status dictionary confirming the saved card details.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("pokemon_cards").document(card_id)
    card_data = {
        "id": card_id,
        "name": name,
        "set": set_name,
        "type": card_type,
        "rarity": rarity,
        "condition": condition,
        "estimated_value_usd": float(estimated_value_usd),
        "available_for_trade": available_for_trade,
        "owner": owner,
        "notes": notes or "",
    }
    doc_ref.set(card_data)
    return {"status": "success", "message": f"Card '{name}' ({card_id}) saved to Firestore.", "card": card_data}


def evaluate_trade_fairness(
    offered_card_names: List[str],
    requested_card_names: List[str],
) -> Dict[str, Any]:
    """Evaluates whether a proposed card trade is fair based on current catalog market values.

    Args:
        offered_card_names: List of card names offered by the counterparty (what you would receive).
        requested_card_names: List of card names requested from you (what you would give away).

    Returns:
        A detailed trade fairness evaluation including side-by-side values, differential, and verdict.
    """
    db = _get_firestore_client()
    docs = list(db.collection("pokemon_cards").stream())
    all_cards = [doc.to_dict() for doc in docs]

    def find_card(query: str):
        q = query.lower()
        for c in all_cards:
            if q in c.get("name", "").lower() or q in c.get("id", "").lower():
                return c
        return None

    offered_details = []
    offered_total = 0.0
    for name in offered_card_names:
        found = find_card(name)
        if found:
            val = float(found.get("estimated_value_usd", 0.0))
            offered_total += val
            offered_details.append({"name": found.get("name"), "value_usd": val, "status": "found"})
        else:
            offered_details.append({"name": name, "value_usd": 0.0, "status": "not_in_catalog"})

    requested_details = []
    requested_total = 0.0
    warnings = []
    for name in requested_card_names:
        found = find_card(name)
        if found:
            val = float(found.get("estimated_value_usd", 0.0))
            requested_total += val
            if not found.get("available_for_trade", True):
                warnings.append(f"Warning: '{found.get('name')}' is marked as NOT available for trade.")
            requested_details.append({"name": found.get("name"), "value_usd": val, "status": "found"})
        else:
            requested_details.append({"name": name, "value_usd": 0.0, "status": "not_in_catalog"})

    diff = offered_total - requested_total
    if requested_total > 0:
        ratio = (offered_total / requested_total) * 100
    else:
        ratio = 100.0 if offered_total == 0 else 999.0

    if diff >= 20.0 or ratio >= 115.0:
        verdict = "Favorable (You gain significant value)"
    elif diff <= -20.0 or ratio <= 85.0:
        verdict = "Unfavorable (You lose significant value)"
    else:
        verdict = "Fair Trade (Values are closely balanced)"

    return {
        "verdict": verdict,
        "offered_total_usd": round(offered_total, 2),
        "requested_total_usd": round(requested_total, 2),
        "net_difference_usd": round(diff, 2),
        "value_ratio_pct": round(ratio, 1),
        "offered_breakdown": offered_details,
        "requested_breakdown": requested_details,
        "warnings": warnings,
    }


def manage_wishlist(
    action: str,
    card_name: str,
    target_price_usd: Optional[float] = None,
    priority: str = "Medium",
) -> Dict[str, Any]:
    """Manages the collector's card wishlist in Firestore.

    Args:
        action: 'add', 'remove', or 'list'.
        card_name: Name of the card (for add/remove).
        target_price_usd: Optional max price you are willing to pay/trade for it.
        priority: 'High', 'Medium', or 'Low' priority.

    Returns:
        Status message and the current wishlist items.
    """
    db = _get_firestore_client()
    collection = db.collection("collector_wishlist")
    action_lower = action.lower()

    if action_lower == "add":
        doc_id = card_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        data = {
            "card_name": card_name,
            "target_price_usd": float(target_price_usd) if target_price_usd is not None else None,
            "priority": priority,
        }
        collection.document(doc_id).set(data)
        message = f"Added '{card_name}' to wishlist with {priority} priority."
    elif action_lower == "remove":
        doc_id = card_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        collection.document(doc_id).delete()
        message = f"Removed '{card_name}' from wishlist."
    elif action_lower == "list":
        message = "Fetched current wishlist."
    else:
        return {"error": f"Unknown action '{action}'. Use 'add', 'remove', or 'list'."}

    current_items = [doc.to_dict() for doc in collection.stream()]
    return {"message": message, "wishlist": current_items}


def generate_trade_offer_sheet(
    trader_name: str,
    offered_cards: List[str],
    requested_cards: List[str],
    cash_compensation_usd: float = 0.0,
    shipping_terms: str = "Padded bubble mailer with tracking",
) -> Dict[str, Any]:
    """Generates and logs an official trade offer sheet in Firestore.

    Args:
        trader_name: Name or handle of the trading counterparty.
        offered_cards: List of cards offered to you.
        requested_cards: List of cards requested from your collection.
        cash_compensation_usd: Any cash added to balance the trade (positive if they add cash, negative if you add).
        shipping_terms: Agreed packaging and shipping details.

    Returns:
        The generated trade ticket record saved to Firestore.
    """
    db = _get_firestore_client()
    import time
    trade_id = f"trade-{int(time.time())}"

    eval_result = evaluate_trade_fairness(
        offered_card_names=offered_cards,
        requested_card_names=requested_cards,
    )

    trade_record = {
        "trade_id": trade_id,
        "trader_name": trader_name,
        "offered_cards": offered_cards,
        "requested_cards": requested_cards,
        "cash_compensation_usd": float(cash_compensation_usd),
        "shipping_terms": shipping_terms,
        "fairness_verdict": eval_result.get("verdict"),
        "offered_total_usd": eval_result.get("offered_total_usd"),
        "requested_total_usd": eval_result.get("requested_total_usd"),
        "net_difference_usd": eval_result.get("net_difference_usd"),
        "status": "Proposed",
    }
    db.collection("trade_offers").document(trade_id).set(trade_record)

    return {
        "status": "success",
        "trade_id": trade_id,
        "summary": (
            f"Trade offer #{trade_id} with {trader_name} created successfully! "
            f"Verdict: {eval_result.get('verdict')} (Difference: ${eval_result.get('net_difference_usd'):+.2f})"
        ),
        "record": trade_record,
    }


def fetch_pokemon_tcg_cards(card_name: str, max_results: int = 5) -> Dict[str, Any]:
    """Fetches real official Pokémon Trading Card Game (TCG) cards from the open TCGdex Card API.

    Args:
        card_name: Name of the card to search for (e.g. 'Charizard', 'Gengar', 'Rayquaza', 'Pikachu').
        max_results: Max number of card printings/variants to retrieve (default 5).

    Returns:
        Dictionary containing real card printings with card ID, name, set, rarity, HP, types, and official card image URL.
    """
    import urllib.request
    import urllib.parse
    import json

    encoded_name = urllib.parse.quote(card_name.strip())
    search_url = f"https://api.tcgdex.net/v2/en/cards?name={encoded_name}"
    req = urllib.request.Request(search_url, headers={"User-Agent": "BuildWithGeminiAgent/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            card_items = json.loads(resp.read().decode("utf-8"))

        if not card_items or not isinstance(card_items, list):
            return {"status": "empty", "message": f"No TCG cards found matching '{card_name}'."}

        detailed_cards = []
        for item in card_items[:max_results]:
            c_id = item.get("id")
            detail_url = f"https://api.tcgdex.net/v2/en/cards/{c_id}"
            try:
                detail_req = urllib.request.Request(detail_url, headers={"User-Agent": "BuildWithGeminiAgent/1.0"})
                with urllib.request.urlopen(detail_req, timeout=5) as d_resp:
                    data = json.loads(d_resp.read().decode("utf-8"))

                detailed_cards.append({
                    "card_id": data.get("id"),
                    "name": data.get("name"),
                    "set": data.get("set", {}).get("name") if isinstance(data.get("set"), dict) else data.get("set"),
                    "rarity": data.get("rarity"),
                    "hp": data.get("hp"),
                    "types": data.get("types", []),
                    "stage": data.get("stage"),
                    "illustrator": data.get("illustrator"),
                    "image_url": f"{data.get('image')}/high.webp" if data.get("image") else None,
                })
            except Exception:
                # Fallback to summary item if detail fetch fails
                detailed_cards.append({
                    "card_id": item.get("id"),
                    "name": item.get("name"),
                    "image_url": f"{item.get('image')}/high.webp" if item.get("image") else None,
                })

        return {
            "status": "success",
            "search_query": card_name,
            "total_matches_found": len(card_items),
            "cards": detailed_cards,
        }
    except Exception as e:
        return {"status": "error", "message": f"Error querying Pokémon TCG card API: {str(e)}"}


async def generate_card_artwork(
    prompt: str,
    card_name: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generates custom Pokemon card artwork using the gemini-3.1-flash-lite-image model in global region.

    Saves the generated image as an ADK artifact (so it appears in Playground Artifacts),
    and uploads the image bytes to the public Cloud Storage bucket, returning its public URL.

    Args:
        prompt: Visual description for the card art (e.g. 'holographic vintage illustration of dark gengar in a haunted forest').
        card_name: Name of the card being illustrated (e.g. 'Dark Gengar').
        tool_context: The ADK ToolContext injected by the framework.

    Returns:
        Dictionary containing the public Cloud Storage image URL, artifact filename, and status.
    """
    clean_slug = card_name.strip().lower().replace(" ", "-").replace("(", "").replace(")", "")
    filename = f"{clean_slug}-{int(time.time())}.jpg"

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="global",
    )

    image_prompt = (
        f"Detailed collectible trading card game artwork for Pokémon card '{card_name}': {prompt}. "
        "High quality, vibrant, suitable for card illustration."
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=image_prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"status": "error", "message": "Model generated a response but no image bytes were found."}

        # 1. Save as ADK artifact so it appears in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        try:
            await tool_context.save_artifact(filename, artifact_part)
        except Exception as e:
            # Continue even if artifact service isn't active in CLI runner
            pass

        # 2. Upload bytes directly to public GCS bucket (without writing to local file)
        storage_client = _get_storage_client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "card_name": card_name,
            "artifact_filename": filename,
            "public_image_url": public_url,
            "message": f"Successfully generated artwork for '{card_name}' and published to Cloud Storage.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate card artwork: {str(e)}"}


sandbox_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name=SANDBOX_ID,
    agent_engine_resource_name=AGENT_ENGINE_ID,
)


def run_python_in_sandbox(code: str) -> dict:
    """Execute Python code in the Agent Engine sandbox and return stdout and stderr.

    Args:
        code: The Python code to run in the sandbox.
    """
    class _DummyCtx:
        session = type("Session", (), {"state": {}})()
        invocation_id = "sandbox_call"
        branch = None

    from google.adk.code_executors.code_execution_utils import CodeExecutionInput
    res = sandbox_executor.execute_code(_DummyCtx(), CodeExecutionInput(code=code))
    return {
        "stdout": res.stdout,
        "stderr": res.stderr,
    }


def python_interpreter(code: str) -> dict:
    """Execute Python code in the Agent Engine sandbox. Alias for code execution.

    Args:
        code: The Python code string to execute.
    """
    return run_python_in_sandbox(code)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert Pokemon Card Collector and Trading Assistant. "
        "You help collectors inspect catalog cards, evaluate proposed trades for fairness, "
        "manage the collector's wishlist, create trade offer sheets, look up real Pokemon TCG cards via TCGdex, "
        "generate custom card artwork using gemini-3.1-flash-lite-image, "
        "and add or update cards in Firestore. "
        "You remember the user's stated preferences, favorite Pokemon, budget constraints, "
        "and facts from previous conversations and use them to personalize your advice and trade evaluations. "
        "You also have access to a secure Python Code Execution sandbox environment via Agent Engine to run mathematical "
        "and statistical calculations."
    ),
    workflow_description="Analyze the collector's request, invoke tools as needed, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=sandbox_executor,
    tools=[
        PreloadMemoryTool(),
        list_pokemon_cards,
        search_pokemon_card,
        add_or_update_pokemon_card,
        evaluate_trade_fairness,
        manage_wishlist,
        generate_trade_offer_sheet,
        fetch_pokemon_tcg_cards,
        generate_card_artwork,
        run_python_in_sandbox,
        python_interpreter,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
