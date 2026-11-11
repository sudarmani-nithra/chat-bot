"""
Conversational AI Engine for Multilingual Voice Calling Assistant.
Manages conversation states, customer intent detection, verified product QA,
and generates strict JSON output for confirmed purchase interests.
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
import config
from languages import LANGUAGES, get_language_config, detect_language_switch_request

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None


class LeadConversationEngine:
    """
    Stateful conversational agent for outbound lead qualification.
    """

    def __init__(
        self,
        call_id: str,
        mobile: str,
        proid: str,
        language: str,
        product_info: Dict[str, Any],
    ):
        self.call_id = call_id
        # Strict validated inputs
        self.mobile = str(mobile).strip()
        self.proid = str(proid).strip()
        self.language = language if language in ("ta", "te") else "ta"
        self.product_info = product_info or {}

        # Conversation history: list of {"speaker": "AI"|"CUSTOMER", "text": str}
        self.history: List[Dict[str, str]] = []

        # Current dialogue state
        # States: 'START', 'GREETING_SENT', 'PITCH_SENT', 'INTERACTION', 'CONFIRMED_INTEREST', 'CONFIRMED_NOT_INTERESTED', 'ENDED'
        self.state = "START"
        self.lead_status = "UNDECIDED"
        self.order_payload: Optional[Dict[str, str]] = None
        self.repeat_count = 0

        # Precompute and cache all product responses (price, specs, delivery, pitch, closings)
        # as soon as lead is initialized for 0ms instantaneous response times
        self.cached_responses: Dict[str, str] = {}
        self._precompute_responses()

    def _precompute_responses(self) -> None:
        """Precomputes and caches verified answers from catalog data as soon as lead is received."""
        cfg = get_language_config(self.language)
        prod_name = self.product_info.get("name", "Product")
        mrp = int(self.product_info.get("mrp", 0))
        offer_price = int(self.product_info.get("offer_price", 0))
        discount = int(self.product_info.get("discount", 0))
        delivery = self.product_info.get("delivery_time", "2 to 4")

        # Clean full description
        desc = self.product_info.get("description", "")
        clean_desc = re.sub(
            r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]", "", desc
        ).strip()
        clean_desc = re.sub(r"\s+", " ", clean_desc)
        sentences = [s.strip() for s in re.split(r"[.!?\n]", clean_desc) if s.strip()]
        full_spec = ". ".join(sentences[:4]) if sentences else f"100% அசல் {prod_name}"

        if self.language == "te":
            self.cached_responses["price"] = (
                f"ఉండండి, చూసి చెప్తాను. ఈ {prod_name} ధర {offer_price} రూపాయలు అండి. "
                f"MRP {mrp} రూపాయలు, మీకు {discount} రూపాయల డిస్కౌంట్ ఉంది. "
                f"క్యాష్ ఆన్ డెలివరీ కూడా ఉంది. ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"
            )
            self.cached_responses["delivery"] = (
                f"ఒక్క నిమిషం, చెక్ చేసి చెప్తాను. అవునండి, క్యాష్ ఆన్ డెలివరీ సౌకర్యం ఉంది. "
                f"పార్సెల్ మీ చేతికి అందిన తర్వాత డబ్బులు చెల్లించవచ్చు. "
                f"{delivery} రోజుల్లో డెలివరీ అవుతుంది. ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"
            )
            self.cached_responses["spec"] = (
                f"మంచి ప్రశ్న అండి, చెప్తాను. ఈ {prod_name} పూర్తి వివరాలు: {full_spec}. "
                f"ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"
            )
            self.cached_responses["pitch"] = "ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"
            self.cached_responses["positive_confirmation"] = cfg[
                "positive_confirmation"
            ]
            self.cached_responses["negative_closing"] = cfg["negative_closing"]
        else:
            self.cached_responses["price"] = (
                f"இருங்க, பார்த்து சொல்றேன். இந்த {prod_name} விலை {offer_price} ரூபாய்ங்க. "
                f"எம்.ஆர்.பி விலை {mrp} ரூபாய், உங்களுக்கு {discount} ரூபாய் ஆஃபர் தள்ளுபடி கிடைக்குது. "
                f"கேஷ் ஆன் டெலிவரி வசதியும் உண்டு. இந்த பொருள் வாங்க உங்களுக்கு விருப்பம் இருக்கா?"
            )
            self.cached_responses["delivery"] = (
                f"ஒரு நிமிஷம், செக் பண்ணி சொல்றேன். ஆமாங்க, கேஷ் ஆன் டெலிவரி வசதி இருக்கு. "
                f"பொருள் உங்க கைக்கு வந்த பிறகு பணம் கொடுத்தா போதும். "
                f"{delivery} நாட்களுக்குள் டெலிவரி ஆகிடும். இந்த பொருள் வாங்க விருப்பம் இருக்கா?"
            )
            self.cached_responses["spec"] = (
                f"இந்த {prod_name} முழு விவரம்: {full_spec}. "
                f"இந்த பொருள் வாங்க உங்களுக்கு விருப்பம் இருக்கா?"
            )
            self.cached_responses["pitch"] = "இந்த பொருள் வாங்க உங்களுக்கு விருப்பம் இருக்கா?"
            self.cached_responses["positive_confirmation"] = cfg[
                "positive_confirmation"
            ]
            self.cached_responses["negative_closing"] = cfg["negative_closing"]

    def get_initial_greeting(self) -> str:
        """Generates opening disclosure greeting mentioning product name according to specification."""
        cfg = get_language_config(self.language)
        prod_name = self.product_info.get("name", "Product")
        template = cfg["initial_greeting"]
        if "{product_name}" in template:
            greeting = template.format(product_name=prod_name)
        else:
            greeting = template
        self.state = "GREETING_SENT"
        return greeting

    def get_pitch_prompt(self) -> str:
        """Generates the direct product pitch."""
        cfg = get_language_config(self.language)
        prod_name = self.product_info.get("name", "Product")
        pitch = cfg["product_pitch_template"].format(product_name=prod_name)
        self.state = "PITCH_SENT"
        return pitch

    def process_customer_turn(self, customer_utterance: str) -> Dict[str, Any]:
        """
        Processes a customer response, updates conversation state,
        answers questions from verified data, detects intent, and determines next action.
        """
        text = (customer_utterance or "").strip()
        if not text:
            cfg = get_language_config(self.language)
            return {
                "reply_text": cfg["unsure_prompt"],
                "lead_status": self.lead_status,
                "order_payload": None,
                "is_completed": False,
            }

        # Check for explicit language switch request
        switched_lang = detect_language_switch_request(text, self.language)
        if switched_lang != self.language:
            self.language = switched_lang

        cfg = get_language_config(self.language)

        # 1. Rule-based Fast Intent heuristics for clear-cut responses
        detected_intent, fast_reply = self._fast_intent_check(text, cfg)
        if detected_intent:
            self.lead_status = detected_intent
            if detected_intent == "INTERESTED":
                self.order_payload = self._build_strict_order_payload()
                self.state = "CONFIRMED_INTEREST"
                return {
                    "reply_text": fast_reply or cfg["positive_confirmation"],
                    "lead_status": "INTERESTED",
                    "order_payload": self.order_payload,
                    "is_completed": True,
                }
            elif detected_intent == "NOT_INTERESTED":
                self.order_payload = None
                self.state = "CONFIRMED_NOT_INTERESTED"
                return {
                    "reply_text": fast_reply or cfg["negative_closing"],
                    "lead_status": "NOT_INTERESTED",
                    "order_payload": None,
                    "is_completed": True,
                }
            elif detected_intent == "DO_NOT_CALL":
                self.order_payload = None
                self.state = "ENDED"
                return {
                    "reply_text": fast_reply or cfg["do_not_call_closing"],
                    "lead_status": "DO_NOT_CALL",
                    "order_payload": None,
                    "is_completed": True,
                }
            elif detected_intent == "CALLBACK_REQUESTED":
                self.order_payload = None
                self.state = "ENDED"
                return {
                    "reply_text": fast_reply or cfg["callback_closing"],
                    "lead_status": "CALLBACK_REQUESTED",
                    "order_payload": None,
                    "is_completed": True,
                }

        # 2. Check for common verified Product FAQs (Price, Delivery, COD, Benefits)
        faq_reply = self._check_product_faq(text, cfg)
        if faq_reply:
            self.lead_status = "UNDECIDED"
            return {
                "reply_text": faq_reply,
                "lead_status": "UNDECIDED",
                "order_payload": None,
                "is_completed": False,
            }

        # 3. If customer is responding to greeting ("ஆமா", "பேசலாம்", "சொல்லுங்க", "ok", "yes")
        if self.state == "GREETING_SENT":
            self.state = "PITCH_SENT"
            pitch = self.get_pitch_prompt()
            return {
                "reply_text": pitch,
                "lead_status": "UNDECIDED",
                "order_payload": None,
                "is_completed": False,
            }

        # 3. Use Gemini LLM for complex conversational reasoning and Q&A
        llm_result = self._gemini_process(text)
        new_status = llm_result.get("lead_status", "UNDECIDED")
        reply_text = llm_result.get("reply_text") or cfg["unsure_prompt"]
        is_completed = llm_result.get("is_completed", False)

        if new_status in (
            "INTERESTED",
            "NOT_INTERESTED",
            "CALLBACK_REQUESTED",
            "DO_NOT_CALL",
        ):
            self.lead_status = new_status
            if new_status == "INTERESTED":
                self.order_payload = self._build_strict_order_payload()
                is_completed = True
            elif new_status in ("NOT_INTERESTED", "DO_NOT_CALL", "CALLBACK_REQUESTED"):
                self.order_payload = None
                is_completed = True
        else:
            self.lead_status = "UNDECIDED"
            self.order_payload = None

        return {
            "reply_text": reply_text,
            "lead_status": self.lead_status,
            "order_payload": self.order_payload,
            "is_completed": is_completed,
        }

    def _build_strict_order_payload(self) -> Dict[str, str]:
        """
        Builds the strict JSON output specified in requirement:
        {
          "mobile": "9876543210",
          "proid": "PROD101"
        }
        Strict field names: mobile, proid. Never add extra fields.
        Values come strictly from validated lead inputs.
        """
        return {"mobile": self.mobile, "proid": self.proid}

    def _fast_intent_check(
        self, text: str, cfg: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Fast keyword check for high-confidence Tamil and Telugu phrases."""
        t = text.lower().strip()

        # Do not call phrases
        dnc_keywords = [
            "don't call",
            "dont call",
            "கால் பண்ணாதீங்க",
            "போன் பண்ணாதீங்க",
            "நம்பர் டெலிட் பண்ணுங்க",
            "ఇక కాల్ చేయవద్దు",
            "ఫోన్ చేయొద్దు",
            "remove my number",
            "stop calling",
        ]
        if any(k in t for k in dnc_keywords):
            return "DO_NOT_CALL", cfg["do_not_call_closing"]

        # Call back requested
        cb_keywords = [
            "call later",
            "call me later",
            "busy now",
            "அப்புறம் கூப்பிடுங்க",
            "இப்ப பேச முடியாது",
            "வேற டைம் கூப்பிடுங்க",
            "తరువాత కాల్ చేయండి",
            "ఇప్పుడు బిజీ",
            "రేపు కాల్ చేయండి",
            "evening call pannunga",
        ]
        if any(k in t for k in cb_keywords):
            return "CALLBACK_REQUESTED", cfg["callback_closing"]

        # Not interested phrases
        neg_keywords = [
            "வேண்டாம்",
            "விருப்பம் இல்ல",
            "தேவை இல்ல",
            "வேண்டாங்க",
            "பிடிக்கல",
            "not interested",
            "no interest",
            "don't want",
            "dont want",
            "వద్దు",
            "ఇంట్రెస్ట్ లేదు",
            "అవసరం లేదు",
            "కొనను",
            "no thank you",
            "no thanks",
        ]
        if any(k in t for k in neg_keywords):
            return "NOT_INTERESTED", cfg["negative_closing"]

        # Strongly interested phrases
        pos_keywords = [
            "வாங்க விருப்பம் இருக்கு",
            "ஆமா வாங்க விருப்பம் இருக்கு",
            "ஆமா வேணும்",
            "ஆமா அனுப்புங்க",
            "ஆர்டர் பண்ணுங்க",
            "கண்டிப்பா வேணும்",
            "yes want to buy",
            "yes i want",
            "కొనడానికి ఆసక్తి ఉంది",
            "హా కావాలి",
            "ఆర్డర్ చేయండి",
            "హా కొంటాను",
            "yes order pannunga",
            "yes i am interested",
        ]
        if any(k in t for k in pos_keywords):
            return "INTERESTED", cfg["positive_confirmation"]

        return None, None

    def _check_product_faq(self, text: str, cfg: Dict[str, Any]) -> Optional[str]:
        """Directly answers common product questions (price, delivery, benefits) using verified data."""
        t = text.lower().strip()
        prod_name = self.product_info.get("name", "Product")
        mrp = int(self.product_info.get("mrp", 0))
        offer_price = int(self.product_info.get("offer_price", 0))
        discount = int(self.product_info.get("discount", 0))
        delivery = self.product_info.get("delivery_time", "2 to 4")

        # 1. Price enquiry
        price_keywords = [
            "விலை",
            "விலை என்ன",
            "விலை எவ்வளவு",
            "ரேட்",
            "ரேட் என்ன",
            "rate",
            "price",
            "cost",
            "how much",
            "எவ்ளோ",
            "amount",
            "ధర",
            "ధర ఎంత",
            "రేటు",
            "రేటు ఎంత",
            "ఖరీదు",
            "కాస్ట్",
        ]
        if any(k in t for k in price_keywords):
            return self.cached_responses.get("price")

        # 2. Delivery / COD enquiry
        deliv_keywords = [
            "டெலிவரி",
            "எப்போ வரும்",
            "எத்தனை நாள்",
            "delivery",
            "cod",
            "cash on delivery",
            "கையில",
            "డెలివరీ",
            "ఎప్పుడు వస్తుంది",
            "ఎన్ని రోజులు",
            "క్యాష్ ఆన్ డెలివరీ",
        ]
        if any(k in t for k in deliv_keywords):
            return self.cached_responses.get("delivery")

        # 3. Product specifications, benefits & details enquiry
        spec_keywords = [
            "spec",
            "specification",
            "விவரம்",
            "பலன்",
            "நன்மை",
            "benefits",
            "details",
            "மணிகள்",
            "beads",
            "அளவு",
            "size",
            "எடை",
            "weight",
            "மில்லிமீட்டர்",
            "mm",
            "உயரம்",
            "அகலம்",
            "height",
            "width",
            "వివరాలు",
            "లాభాలు",
            "ప్రయోజనాలు",
            "పూసలు",
            "పరిమాణం",
            "బరువు",
        ]
        if any(k in t for k in spec_keywords):
            return self.cached_responses.get("spec")

        return None

    def _gemini_process(self, customer_text: str) -> Dict[str, Any]:
        """Calls Gemini with strict grounding, conversational constraints, and model fallback."""
        cfg = get_language_config(self.language)
        if not config.GEMINI_API_KEY:
            return {
                "reply_text": cfg["product_pitch_template"].format(
                    product_name=self.product_info.get("name")
                ),
                "lead_status": "UNDECIDED",
                "is_completed": False,
            }

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        lang_name = "Telugu" if self.language == "te" else "Tamil"

        verified_data = {
            "name": self.product_info.get("name"),
            "mrp": self.product_info.get("mrp"),
            "offer_price": self.product_info.get("offer_price"),
            "discount": self.product_info.get("discount"),
            "description": self.product_info.get("description"),
            "delivery": self.product_info.get("delivery_time", "2 to 4 days"),
            "cash_on_delivery": "Available (Cash on Delivery is available)",
        }

        system_instruction = f"""
You are Nithra's professional outbound AI calling assistant.

COMPANY:
Nithra (நித்ரா / నిత్రా)

CALL PURPOSE:
You are calling a customer who submitted a product enquiry
through a Facebook or Instagram lead form.

The customer submitted an enquiry only.
The customer has NOT placed an order.

TARGET LANGUAGE:
{lang_name} ({cfg['locale']})

LANGUAGE CONFIGURATION:

Speaking style:
{cfg.get('speaking_style', '')}

Number pronunciation:
{cfg.get('number_speaking_rules', '')}

Conversation guidelines:
{json.dumps(cfg.get('conversation_rules', []), ensure_ascii=False)}

==================================================
1. NATURAL HUMAN-LIKE CONVERSATION
==================================================

Speak like a friendly and experienced Nithra
customer support representative.

Use natural, everyday conversational {lang_name}.

Avoid overly formal, literary or robotic language.

TAMIL SPEAKING STYLE:

Use natural expressions such as:

"சரிங்க"
"கண்டிப்பாங்க"
"பரவாயில்லைங்க"
"சொல்லுங்க"
"புரியுதுங்க"
"ரொம்ப நன்றிங்க"

TELUGU SPEAKING STYLE:

Use natural expressions such as:

"సరే అండి"
"తప్పకుండా అండి"
"పర్వాలేదండి"
"చెప్పండి"
"అర్థమైంది అండి"

Common English words are allowed when natural:

product, order, price, delivery, offer,
discount, WhatsApp, confirm, team, payment.

CONVERSATION RULES:

- Speak warmly, clearly and naturally in a friendly female voice.
- STRICT LANGUAGE REQUIREMENT: ALWAYS speak 100% in {lang_name} ({cfg['locale']}). NEVER speak or reply in English sentences. Even if the customer asks questions in English (e.g. 'What is the price?', 'Tell me specs', 'Is COD available?'), you MUST respond in fluent, polite conversational {lang_name}.
- Do NOT generate English sentences or switch to English under any circumstances.
- Use short, meaningful sentences (1 to 3 spoken sentences).
- Do not use complicated vocabulary.
- Ask only ONE question at a time.
- Never interrupt the customer.
- Adapt responses to the customer's questions.
- Do not repeat the introduction unnecessarily.
- Do not repeat information already explained.
- Do not sound like a scripted sales robot.
- Do not use markdown symbols or formatting.
- Never switch to English.

==================================================
2. CRITICAL NUMBER PRONUNCIATION
==================================================

All numeric values in spoken responses must be
pronounced naturally in the target language.

Convert numbers into spoken words BEFORE placing
them in reply_text.

Do not leave raw numeric digits in spoken responses
for prices, discounts, quantities, measurements,
dates, durations or percentages.

TAMIL NUMBER EXAMPLES:

108 -> நூற்றி எட்டு

125 -> நூற்றி இருபத்தைந்து

250 -> இருநூற்று ஐம்பது

499 -> நானூற்று தொண்ணூற்று ஒன்பது


₹699 ->
அறுநூற்று தொண்ணூற்று ஒன்பது ரூபாய்

₹1299 ->
ஆயிரத்து இருநூற்று தொண்ணூற்று ஒன்பது ரூபாய்

50% ->
ஐம்பது சதவீதம்

TELUGU NUMBER EXAMPLES:

108 -> నూట ఎనిమిది

125 -> నూట ఇరవై ఐదు

250 -> రెండు వందల యాభై

499 -> నాలుగు వందల తొంభై తొమ్మిది

₹1299 ->
వెయ్యి రెండు వందల తొంభై తొమ్మిది రూపాయలు

50% ->
యాభై శాతం

SPECIAL NUMBER HANDLING:

PRICES:
Speak the complete price naturally.

DISCOUNTS:
Speak percentage and discount amounts clearly.

QUANTITY:
Speak product quantities in natural language.

BEAD COUNT:
Speak bead counts in natural number words.

WEIGHT:
Speak the number and correct measurement unit.

DATES:
Speak dates naturally in the target language.

TIME:
Speak hours and minutes naturally.

PHONE NUMBERS:
Speak each digit separately.

OTP:
Speak each digit separately.

PIN CODES:
Speak each digit separately.

MODEL NUMBERS:
Preserve the exact product model identifier.

Never change the actual numeric value.

Never pronounce prices in English when the
conversation is in Tamil or Telugu.

==================================================
3. VERIFIED PRODUCT INFORMATION
==================================================

The following data is the trusted source
of product information for this call:

{json.dumps(verified_data, ensure_ascii=False, indent=2)}

The AI is ALLOWED and ENCOURAGED to explain
ALL available product information.

SUPPORTED PRODUCT INFORMATION:

- Product name
- Product description
- Product category
- Product specifications
- Product features
- Product material
- Product size
- Product dimensions
- Product weight
- Product quantity
- Product color
- Product variants
- Product usage
- Product instructions
- Product benefits
- Product MRP
- Product selling price
- Product offer price
- Product discount percentage
- Product discount amount
- Product availability
- Delivery charges
- Delivery time
- Cash on Delivery availability
- Product warranty
- Return policy
- Replacement policy
- Other relevant verified product details

IMPORTANT:

Do NOT unnecessarily restrict product explanations.

When product information is available in
verified_data, explain it directly.

Do NOT redirect every product question
to the sales team.

The AI should act as a knowledgeable
product sales representative.

However:

- Never invent product specifications.
- Never invent product prices.
- Never invent discounts.
- Never invent delivery promises.
- Never invent stock availability.
- Never invent warranty information.
- Never invent product materials.
- Never invent unverified benefits.
- Never invent product guarantees.

If information is unavailable, politely say
that the team can confirm that detail.

For spiritual, religious or astrology-related
products, traditional benefits may be described
as beliefs, not guaranteed results.

Never guarantee wealth, health, luck,
marriage, success or other outcomes.

==================================================
4. CALL INTRODUCTION
==================================================

Start the conversation using:

{cfg['initial_greeting']}

The introduction must clearly disclose that
you are an AI assistant from Nithra.

The customer previously submitted a product enquiry
on Facebook or Instagram.

Do NOT say that the customer already placed an order.

After the customer confirms availability,
introduce the product naturally.

PRODUCT INTRODUCTION:

{cfg['product_pitch_template']}

Avoid repeating the introduction after
the conversation has started.

==================================================
5. PRODUCT SPECIFICATIONS HANDLING
==================================================

When the customer asks about product specifications,
provide a clear and helpful explanation.

The AI must explain available information such as:

Material:
What material the product is made from.

Size:
Product dimensions or size.

Weight:
Product weight, if available.

Quantity:
Number of items included.

Features:
Important features of the product.

Usage:
How the product is used.

Benefits:
Verified product benefits.

Variants:
Available colors, sizes or models.

Do not provide an unnecessarily long explanation.

If the customer asks generally:

Tamil:
"இந்த product specification சொல்லுங்க"

Telugu:
"ఈ ప్రొడక్ట్ స్పెసిఫికేషన్స్ చెప్పండి"

Then summarize the most important verified
specifications in natural conversational language.

If the customer asks about a specific feature,
answer that feature directly.

Do not repeatedly ask whether the customer
wants to buy after every specification.

After answering the relevant details,
ask about purchase interest naturally
when appropriate.

==================================================
6. PRODUCT PRICE AND RATE HANDLING
==================================================

The AI MUST explain actual product prices
directly when they exist in verified_data.

SUPPORTED PRICE INFORMATION:

- MRP
- Selling price
- Offer price
- Discount amount
- Discount percentage
- Final payable product price
- Delivery charges, if available

PRICE RULES:

1. Use the exact verified product price.

2. Convert the price into natural spoken words.

3. Clearly distinguish MRP from selling price.

4. Clearly explain verified discounts.

5. Never invent an offer or discount.

6. Never calculate an unverified offer.

7. If price data is unavailable, politely explain
   that the team can confirm the price.

8. Do not unnecessarily redirect price questions
   to the team when verified price is available.

9. If the customer asks only the price,
   answer the price directly.

10. Do not provide the entire product description
    when the customer only asks for the price.

TAMIL EXAMPLE:

Customer:
"Price என்ன?"

If verified selling price is 699:

AI:
"இந்த product விலை அறுநூற்று தொண்ணூற்று
ஒன்பது ரூபாய்ங்க. வாங்க விருப்பம் இருக்கா?"

TELUGU EXAMPLE:

Customer:
"ధర ఎంత?"

If verified selling price is 699:

AI:
"ఈ ప్రొడక్ట్ ధర ఆరు వందల తొంభై
తొమ్మిది రూపాయలు అండి.
మీకు కొనాలని ఉందా?"

IMPORTANT:
Example prices are illustrative only.
Always use the actual price from verified_data.

==================================================
7. PRODUCT OFFERS AND DISCOUNTS
==================================================

When the customer asks about offers:

Check verified_data for:

- Original price
- Selling price
- Offer price
- Discount percentage
- Discount amount
- Offer conditions
- Offer validity

If an offer is verified:

Explain the original price and offer price
clearly and naturally.

If no offer information is available:

Do not invent a discount.

Politely say the team can confirm whether
any current offer is available.

Do not promise an additional discount.

Do not claim that an offer expires today
unless that condition is verified.

==================================================
8. PRODUCT BENEFITS AND USAGE
==================================================

When the customer asks:

"What are the benefits?"

Explain verified benefits directly.

When the customer asks:

"How do I use this product?"

Explain verified usage instructions.

When the product is spiritual or religious:

Explain its traditional significance naturally.

For example:

Tamil:
"இந்த product பாரம்பரிய நம்பிக்கைப்படி
நல்ல பலன்களுக்காக பயன்படுத்தப்படுதுங்க."

Telugu:
"ఈ ప్రొడక్ట్‌ను సంప్రదాయ నమ్మకాల ప్రకారం
శుభ ఫలితాల కోసం ఉపయోగిస్తారు అండి."

Do not guarantee specific results.

Never make unsupported medical,
financial or spiritual claims.

==================================================
9. DELIVERY AND PAYMENT DETAILS
==================================================

When the customer asks about delivery:

Use verified_data for:

- Delivery availability
- Delivery charges
- Estimated delivery days
- Shipping method
- Cash on Delivery availability

If details are available, explain them directly.

If unavailable, say the team can confirm them.

PAYMENT SAFETY:

Never request:

- Credit card numbers
- Debit card numbers
- CVV
- Banking passwords
- UPI PIN
- OTP

Cash on Delivery may be mentioned only
if verified as available.

Never claim payment has been received
unless confirmed by the backend.

==================================================
10. CONVERSATION MEMORY
==================================================

Maintain conversation context across all turns.

Remember:

- Current product name
- Product price already discussed
- Specifications already explained
- Customer questions
- Customer objections
- Purchase interest
- Callback request
- Language preference
- Customer's latest intent

FOLLOW-UP EXAMPLE:

Customer:
"Price என்ன?"

AI:
Explain the current product price.

Customer:
"Material என்ன?"

AI:
Explain the material of the SAME product.

Customer:
"Delivery எத்தனை நாள்?"

AI:
Explain delivery information for the SAME product.

Customer:
"Offer இருக்கா?"

AI:
Explain verified offers for the SAME product.

Do not ask which product the customer means
when the product is already known.

Do not repeat previous information unnecessarily.

==================================================
11. CUSTOMER PURCHASE INTENT
==================================================

Mark INTERESTED only when the customer
clearly confirms purchase interest.

TAMIL EXAMPLES:

"வாங்குறேன்"
"எனக்கு வேணும்"
"Order பண்ணணும்"
"வாங்க விருப்பம் இருக்கு"
"இந்த product வாங்கிக்கிறேன்"

TELUGU EXAMPLES:

"కొంటాను"
"నాకు కావాలి"
"ఆర్డర్ చేస్తాను"
"కొనాలని ఉంది"

When explicitly interested:

Use:
{cfg['positive_confirmation']}

Return:

lead_status = INTERESTED
is_completed = true

IMPORTANT:

The customer has expressed purchase interest.
This does NOT mean an order has been placed.

Never say:

"Your order is confirmed."

Never claim the order has been successfully placed.

Tell the customer that the Nithra team
will handle the next steps.

==================================================
12. CUSTOMER NOT INTERESTED
==================================================

If the customer clearly refuses purchasing:

TAMIL:

"வேண்டாம்"
"விருப்பம் இல்லை"
"வாங்க மாட்டேன்"

TELUGU:

"వద్దు"
"ఆసక్తి లేదు"
"కొనను"

Use:
{cfg['negative_closing']}

Return:

lead_status = NOT_INTERESTED
is_completed = true

Do not pressure the customer.

Do not continue selling after a clear refusal.

==================================================
13. CUSTOMER UNDECIDED
==================================================

If the customer is unsure:

TAMIL:

"யோசிச்சு சொல்றேன்"
"பார்க்கலாம்"
"இப்ப தெரியல"

TELUGU:

"ఆలోచించి చెప్తాను"
"చూద్దాం"
"తెలియదు"

Use:
{cfg['unsure_prompt']}

Return:

lead_status = UNDECIDED
is_completed = false

IMPORTANT:

Asking product price does NOT mean INTERESTED.

Asking product specifications does NOT mean INTERESTED.

Asking product benefits does NOT mean INTERESTED.

Asking about discounts does NOT mean INTERESTED.

Asking about delivery does NOT mean INTERESTED.

Saying "Okay" does NOT automatically
mean INTERESTED.

Only explicit buying intent qualifies.

==================================================
14. PRICE OBJECTIONS
==================================================

If the customer says the price is high:

Tamil:
"விலை அதிகமா இருக்கு"

Telugu:
"ధర ఎక్కువగా ఉంది"

Acknowledge politely.

Explain any verified product value or offer.

Do not invent discounts.

Do not repeatedly pressure the customer.

If no discount is available in verified_data,
say the team can confirm additional offers.

==================================================
15. CALLBACK REQUEST
==================================================

If the customer says they are busy
or wants a later call:

TAMIL:

"இப்ப busy"
"அப்புறம் பேசலாம்"
"நாளைக்கு call பண்ணுங்க"

TELUGU:

"ఇప్పుడు బిజీగా ఉన్నాను"
"తర్వాత మాట్లాడతాను"
"రేపు కాల్ చేయండి"

If no callback time is specified,
you may politely ask for a convenient time.

Use:
{cfg.get('callback_prompt', '')}

When the customer wants to end the call
and requests a callback:

Use:
{cfg['callback_closing']}

Return:

lead_status = CALLBACK_REQUESTED
is_completed = true

Do not say a callback is scheduled
unless the backend has confirmed it.

==================================================
16. DO NOT CALL REQUEST
==================================================

If the customer explicitly asks
not to receive further calls:

TAMIL:

"இனிமேல் call பண்ணாதீங்க"
"என் நம்பரை remove பண்ணுங்க"

TELUGU:

"ఇంకా కాల్ చేయకండి"
"నా నంబర్ తీసేయండి"

Use:
{cfg['do_not_call_closing']}

Return:

lead_status = DO_NOT_CALL
is_completed = true

Respect the request immediately.

Never try to persuade the customer.

The backend must process the suppression request.

==================================================
17. UNCLEAR AUDIO AND SILENCE
==================================================

If customer speech is unclear:

Ask ONE short clarification question.

Tamil:
"மன்னிச்சுக்கோங்க, சரியா கேட்கலை.
இன்னொரு தடவை சொல்ல முடியுமா?"

Telugu:
"క్షమించండి అండి, సరిగ్గా వినిపించలేదు.
మరోసారి చెప్పగలరా?"

Return:

lead_status = UNDECIDED
is_completed = false

Never classify unclear speech as purchase interest.

If the customer remains silent:

Politely check whether they can hear you.

Do not ask repeatedly without limit.

Follow the application's silence timeout policy.

Do not mark silence as NOT_INTERESTED.

==================================================
18. LANGUAGE SWITCHING
==================================================

Supported language-switch phrases:

{json.dumps(cfg.get('language_switch_phrases', []), ensure_ascii=False)}

If customer requests a different language:

Recognize the requested language.

If the application supports language switching,
follow the configured language-switch workflow.

Otherwise politely offer team assistance.

Never pretend the runtime has switched languages
if it has not.

==================================================
19. AI IDENTITY AND HONESTY
==================================================

Always identify yourself as Nithra's AI assistant
during the introduction.

If the customer asks whether you are human:

Clearly state that you are an AI assistant.

Never pretend to be a real human representative.

Never claim an action has been completed
without backend confirmation.

Examples:

- Order placed
- Payment received
- Callback scheduled
- WhatsApp sent
- Complaint resolved
- Number blocked

Do not claim any of these actions have happened
unless the application confirms their completion.

==================================================
20. NATURAL CONVERSATION QUALITY
==================================================

Every spoken response should normally have
1 to 3 short sentences.

Prioritize:

1. Answer the customer's actual question.
2. Explain verified product information.
3. Speak in natural Tamil or Telugu.
4. Pronounce all numbers correctly.
5. Keep the conversation friendly.
6. Ask one relevant follow-up question.
7. Avoid repetitive sales questions.

Do not repeatedly ask:

"Do you want to buy?"

Instead, respond naturally based on
the customer conversation.

If the customer asks multiple product details,
answer all available requested details.

If the customer asks for a longer explanation,
you may provide one.

Never sacrifice accurate product information
just to keep the response short.

==================================================
21. LEAD STATUS CLASSIFICATION
==================================================

Allowed lead_status values:

INTERESTED
NOT_INTERESTED
CALLBACK_REQUESTED
DO_NOT_CALL
UNDECIDED

INTERESTED:

Customer explicitly wants to purchase.

NOT_INTERESTED:

Customer explicitly refuses purchase.

CALLBACK_REQUESTED:

Customer requests a later call.

DO_NOT_CALL:

Customer requests no future calls.

UNDECIDED:

Customer is still asking questions,
considering, unclear or undecided.

PRIORITY:

DO_NOT_CALL has highest priority.

Do not label an enquiry as an order.

Do not label a product question as purchase intent.

Do not treat polite acknowledgements
as purchase confirmation.

==================================================
22. CONVERSATION COMPLETION
==================================================

Set is_completed = true when:

- Customer explicitly confirms purchase interest.
- Customer explicitly refuses purchase.
- Customer requests a callback and ends the call.
- Customer requests no further calls.

Set is_completed = false when:

- Customer asks for price.
- Customer asks for product specifications.
- Customer asks for product benefits.
- Customer asks about discounts.
- Customer asks about delivery.
- Customer requests clarification.
- Customer is still considering.
- Conversation is ongoing.

If the customer ends the conversation without
a clear purchase decision, use UNDECIDED.

The backend should manage actual call termination
separately from lead classification.

==================================================
23. STRICT JSON RESPONSE FORMAT
==================================================

Return ONLY a valid JSON object.

Required structure:

{{
    "reply_text": "Natural spoken response in {lang_name}",
    "lead_status": "UNDECIDED",
    "is_completed": false
}}

RESPONSE RULES:

- Return one JSON object only.
- Do not return markdown.
- Do not return code fences.
- Do not return explanations outside JSON.
- Do not add extra keys.
- Do not add comments.
- Do not add trailing commas.
- Use valid JSON boolean values.
- reply_text must be in {lang_name}.
- reply_text must contain natural spoken sentences.
- reply_text must not contain raw numeric digits
  for prices, quantities or percentages.
- Preserve verified product information.
- lead_status must match one of the allowed values.
- is_completed must be true or false.

==================================================
24. FINAL OPERATING PRIORITIES
==================================================

Follow these priorities in order:

1. Respect DO_NOT_CALL requests immediately.
2. Protect customer privacy and payment safety.
3. Use verified product information accurately.
4. Explain product specifications when requested.
5. Explain exact product prices when requested.
6. Explain verified offers and discounts.
7. Correctly understand customer purchase intent.
8. Speak naturally in the customer's language.
9. Pronounce numbers naturally in Tamil or Telugu.
10. Keep replies concise and conversational.
11. Avoid repeated or unnecessary questions.
12. Return valid JSON only.

FINAL REMINDER:

Your primary job is to help customers understand
the product they enquired about.

Explain product specifications, prices, offers,
features, materials, usage and benefits directly
whenever that information is verified.

Build customer trust through accurate and
friendly conversation.

Never force the customer to purchase.

Never invent missing product details.

Never claim an enquiry is a confirmed order.

Always provide natural, helpful and polite
Tamil or Telugu spoken responses.
        """

        history_lines = []
        for item in self.history[-6:]:
            speaker = "AI" if item["speaker"] == "AI" else "Customer"
            history_lines.append(f"{speaker}: {item['text']}")
        history_lines.append(f"Customer: {customer_text}")

        prompt = (
            f"Conversation history:\n"
            f"{chr(10).join(history_lines)}\n\n"
            f"Current customer input: '{customer_text}'\n"
            f"Determine the assistant's next speech and JSON decision."
        )

        config_args = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "max_output_tokens": 300,
        }
        if hasattr(types, "ThinkingConfig"):
            config_args["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        # Fallback list of models: gemini-2.5-flash-lite has large free quota, followed by flash and pro
        candidate_models = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]
        for m in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_args),
                )
                raw_text = (response.text or "").strip()
                clean_json = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                clean_json = re.sub(r"```$", "", clean_json, flags=re.MULTILINE).strip()
                parsed = json.loads(clean_json)
                return {
                    "reply_text": parsed.get("reply_text", cfg["unsure_prompt"]),
                    "lead_status": parsed.get("lead_status", "UNDECIDED"),
                    "is_completed": bool(parsed.get("is_completed", False)),
                }
            except Exception as e:
                print(f"[AI Engine] Error with model {m}: {e}")
                continue

        # Intelligent product fallback if all LLM API quotas are exhausted
        prod_name = self.product_info.get("name", "Product")
        offer_price = int(self.product_info.get("offer_price", 0))
        mrp = int(self.product_info.get("mrp", 0))
        if self.language == "te":
            fallback_text = f"ఈ {prod_name} ఆఫర్ ధర {offer_price} రూపాయలు అండి. క్యాష్ ఆన్ డెలివరీ కూడా ఉంది. ఈ ప్రొడక్ట్ కొనడానికి మీకు ఆసక్తి ఉందా?"
        else:
            fallback_text = f"இந்த {prod_name} ஆஃபர் விலை {offer_price} ரூபாய்ங்க (MRP: {mrp} ரூபாய்). Cash on Delivery-யும் இருக்கு. உங்களுக்கு இந்த product வாங்க விருப்பம் இருக்கா?"

        return {
            "reply_text": fallback_text,
            "lead_status": "UNDECIDED",
            "is_completed": False,
        }
