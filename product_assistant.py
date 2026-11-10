"""
E-Commerce Product Assistant Engine for Sri Diya Pooja Store.
Analyzes `mergeProduct` data, answers product questions, performs comparisons,
and enforces strict grounding on provided product information.
Supports 100% audio-only voice interaction without on-screen text.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

PRODUCTS_FILE = Path(__file__).parent / "products.json"

_CACHED_PRODUCTS: Optional[List[Dict[str, Any]]] = None
_CACHED_CATALOG_TEXT: Optional[str] = None


def load_products_data() -> List[Dict[str, Any]]:
    """Loads product catalog from products.json with in-memory caching."""
    global _CACHED_PRODUCTS
    if _CACHED_PRODUCTS is not None:
        return _CACHED_PRODUCTS

    if not PRODUCTS_FILE.exists():
        return []
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _CACHED_PRODUCTS = data.get("mergeProduct", [])
            return _CACHED_PRODUCTS
    except Exception:
        return []


def clean_html(html_text: str) -> str:
    """Removes HTML tags and normalizes whitespace."""
    if not html_text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_text)
    clean = clean.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", clean).strip()


def build_product_context_for_prompt(products: List[Dict[str, Any]]) -> str:
    """
    Builds a structured, human-readable summary of all products in the catalog
    to ground the Gemini model with 100% accuracy.
    """
    global _CACHED_CATALOG_TEXT
    if _CACHED_CATALOG_TEXT is not None and products is _CACHED_PRODUCTS:
        return _CACHED_CATALOG_TEXT

    lines = ["### OFFICIAL PRODUCT CATALOG (mergeProduct):\n"]
    for p in products:
        p_id = p.get("id")
        title = p.get("pname_default") or p.get("english_title")
        mrp = p.get("price")
        final_price = p.get("total_amt")
        discount = p.get("discount")
        stock = p.get("stock")
        stock_status = p.get("stocktext", "In Stock")
        delivery = p.get("delivery", "Nov 10 - 12")
        shipping = p.get("shipping_amt", 0)
        is_cart = p.get("is_cart", 0)
        cart_qty = p.get("cart_qty", 0)
        cart_id = p.get("cart_id", 0)
        is_fav = p.get("is_fav", 0)
        weight = p.get("weight")
        hsn = p.get("hsn_no")
        category = p.get("category_name", "Mala")

        ratings_obj = p.get("ratings", {})
        overall_rating = ratings_obj.get("overall_rating", "N/A")
        total_reviews = ratings_obj.get("reviews", 0)

        # Dynamic desc
        dyn_desc = p.get("dynamic_desc", {})
        heads = dyn_desc.get("desc_head", [])
        descs = dyn_desc.get("description", [])
        details_text = []
        for h, d in zip(heads, descs):
            details_text.append(f"{h}: {clean_html(d)}")

        # Comments snippet
        comments = ratings_obj.get("comments", [])
        reviews_summary = []
        for c in comments[:3]:
            reviews_summary.append(
                f"- {c.get('uname', 'Customer')} ({c.get('rating')}★): \"{c.get('comments')}\""
            )

        product_entry = f"""
---
PRODUCT ID: {p_id}
TITLE: {title}
CATEGORY: {category}
DESCRIPTION & BENEFITS:
{chr(10).join('  - ' + dt for dt in details_text)}
PRICE & DISCOUNT:
  - Final Selling Price (total_amt): ₹{final_price}
  - Shipping Charges: ₹{shipping}
DELIVERY & SPECS:
  - Estimated Delivery: {delivery}
  - Weight: {weight} grams

"""
        lines.append(product_entry)

    catalog_str = "\n".join(lines)
    if products is _CACHED_PRODUCTS:
        _CACHED_CATALOG_TEXT = catalog_str
    return catalog_str


def get_product_system_prompt(products: List[Dict[str, Any]]) -> str:
    """Constructs the strict system prompt for the product assistant."""
    catalog_text = build_product_context_for_prompt(products)

    prompt = f"""You are the official Sri Diya E-Commerce Product Assistant.
Your job is to answer customer questions accurately based ONLY on the provided product catalog below.

CRITICAL INSTRUCTIONS:
1. Identify the correct product using its name, ID, bead count, or other relevant attributes.
2. Retrieve information ONLY from the provided product catalog.
3. Analyze product details such as price (MRP ₹ and final selling total_amt ₹), discount percentage, stock availability,  delivery information.
4. For product comparisons, analyze the relevant products and clearly highlight their differences in a neat markdown comparison table.
5. Do NOT assume, fabricate, or invent information that is not available in the provided data.
6. If the requested information is unavailable in the data, explicitly state: "This information is not present in the provided product data."
7. Use the latest available dynamic values for stock, cart status, wishlist status, and pricing.
8. Answer in a helpful, professional, and structured format using markdown (bolding, bullet points, price breakdowns). If the user asks in Tamil, reply in Tamil; otherwise, reply in clear English.
9. use Shipping Charges to calculate final price 
{catalog_text}
"""
    return prompt

    


def generate_product_voice_response(
    api_key: str,
    user_query: Any,
    history: Optional[List[Dict[str, str]]] = None,
    mime_type: str = "audio/wav",
    voice_model: str = "gemini-2.5-flash-native-audio-latest",
    voice_name: str = "Aoede",
) -> tuple[bytes, str]:
    """
    Directly answers user's product question as audio bytes using Gemini Live Native Audio.
    Accepts text queries or microphone audio recordings with multi-turn conversation context.
    No text is displayed to the user — all product information is delivered strictly via voice.
    Returns (wav_bytes, speech_text).
    """
    from google import genai
    from google.genai import types
    from tamil_voice import synthesize_tamil_speech

    client = genai.Client(api_key=api_key)
    products = load_products_data()
    catalog_text = build_product_context_for_prompt(products)

    system_instruction = f"""You are the Sri Diya Store Voice Assistant.
You speak directly to the customer over voice audio.
Answer the customer's question based ONLY on the provided official product catalog below.

CRITICAL VOICE INSTRUCTIONS:
1. Speak in a warm, natural, and conversational tone suitable for audio listening.
2. Do NOT use markdown symbols (no asterisks, hashes, bullet symbols, or tables) because your response will be spoken aloud to the customer.
3. Pronounce prices, discounts, bead counts, and product names clearly (e.g. say "rupees three hundred and ninety-nine" or "three hundred ninety-nine rupees").
4. If the user asks in Tamil, reply in fluent, natural Tamil speech. If the user asks in English, reply in natural English.
5. Retrieve information ONLY from the provided product catalog. If requested information is unavailable, clearly speak: "This information is not present in our product data."
6. Do not invent any details. Use the exact dynamic values for stock, cart status, and pricing.
7. Keep responses concise (around 2 to 4 spoken sentences) so the audio is fast and crisp.

MULTI-TURN CONVERSATION MEMORY & CONTEXT-AWARE RULES:
- You are having a continuous, multi-turn voice conversation with the customer.
- Carefully track the products and topics discussed in prior turns.
- When the customer asks follow-up questions such as:
    • "How many beads does it have?"
    • "What is the discount?"
    • "Is it in stock?"
    • "What are the benefits?"
    • "How much is it?"
    • "What is the delivery date?"
    • "Can you compare this with another mala?"
  resolve pronouns ("it", "this", "that", "this mala") to the product discussed in earlier turns.
- Never ask the user to repeat the product name if it was already mentioned or implied in previous turns. Answer directly with that product's details.

{catalog_text}
"""

    # Build sanitized alternating multi-turn contents list for Gemini API
    # Limit to the most recent 4 turns (2 user + 2 model) so latency stays constant
    contents_list = []
    if history:
        active_history = history[-4:] if len(history) > 4 else history
        expected_role = "user"
        for turn in active_history:
            role = turn.get("role", "user")
            api_role = "user" if role == "user" else "model"
            turn_text = (turn.get("text") or "").strip()
            if not turn_text:
                continue

            if api_role == expected_role:
                contents_list.append(
                    types.Content(
                        role=api_role, parts=[types.Part.from_text(text=turn_text)]
                    )
                )
                expected_role = "model" if expected_role == "user" else "user"
            else:
                # If same role occurs consecutively, merge text into the previous turn's part
                if contents_list:
                    contents_list[-1].parts.append(
                        types.Part.from_text(text=" " + turn_text)
                    )

        # Ensure history ends with a 'model' turn so that the incoming query starts as a 'user' turn
        while contents_list and contents_list[-1].role == "user":
            contents_list.pop()

    # Current turn
    if isinstance(user_query, (bytes, bytearray)):
        query_parts = [
            types.Part.from_bytes(data=bytes(user_query), mime_type=mime_type),
            types.Part.from_text(
                text="Listen to the user's spoken voice question and answer it accurately based on the conversation history and product catalog."
            ),
        ]
    else:
        query_parts = [types.Part.from_text(text=str(user_query))]

    contents_list.append(types.Content(role="user", parts=query_parts))

    # 1. Ask Gemini to formulate the spoken voice script based on the catalog and history
    # Uses automatic retry & model fallback across flash models in case of 503 high demand spikes
    text_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    last_text_error = None
    speech_text = ""

    for m in text_models:
        for attempt in range(2):
            try:
                config_kwargs: Dict[str, Any] = {
                    "system_instruction": system_instruction,
                    "temperature": 0.2,
                    "max_output_tokens": 300,
                }
                # Disable thinking delay on Gemini 2.5 to generate audio script immediately
                if "2.5" in m and hasattr(types, "ThinkingConfig"):
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_budget=0
                    )

                response = client.models.generate_content(
                    model=m,
                    contents=contents_list,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                if response and (response.text or "").strip():
                    speech_text = response.text.strip()
                    break
            except Exception as e:
                last_text_error = e
                err_str = str(e).lower()
                if (
                    "503" in err_str
                    or "unavailable" in err_str
                    or "high demand" in err_str
                    or "429" in err_str
                ):
                    time.sleep(1.0)
                    continue
                else:
                    break
        if speech_text:
            break

    if not speech_text:
        if last_text_error and (
            "503" in str(last_text_error) or "high demand" in str(last_text_error)
        ):
            speech_text = "I apologize, the service is currently experiencing high demand. Please try asking again in a moment."
        else:
            speech_text = (
                "I could not find information about that in the product catalog."
            )

    # 2. Synthesize the voice audio using Gemini Live Native Audio model
    wav_bytes = synthesize_tamil_speech(
        api_key=api_key, text=speech_text, model_name=voice_model, voice_name=voice_name
    )

    return wav_bytes, speech_text
