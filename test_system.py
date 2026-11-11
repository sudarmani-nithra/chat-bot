"""
Automated Verification Test Suite for Multilingual AI Voice Calling Assistant.
Tests:
- Mobile validation (Indian 10-digit)
- Product catalog lookup (PROD101, 10, etc.)
- Telephony provider pluggability (Simulated vs Real)
- Tamil and Telugu dialogue flows & Greetings
- Intent detection (INTERESTED, NOT_INTERESTED, UNDECIDED, CALLBACK, DO_NOT_CALL)
- Strict JSON output formatting: {"mobile": "...", "proid": "..."}
- Idempotent Telephony Webhook Handling
"""

import sys
import os
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

from app import validate_indian_mobile
import catalog
import database
import telephony
from languages import get_language_config, detect_language_switch_request
from ai_engine import LeadConversationEngine


def run_all_tests():
    print("==================================================")
    print("RUNNING AI VOICE ASSISTANT TEST SUITE")
    print("==================================================")

    # 1. Test Mobile Validation
    print("\n[TEST 1] Mobile Number Validation...")
    assert validate_indian_mobile("9876543210") == "9876543210"
    assert validate_indian_mobile("+91 9876543210") == "9876543210"
    assert validate_indian_mobile("09876543210") == "9876543210"
    assert validate_indian_mobile("919876543210") == "9876543210"

    for invalid in ["12345", "1234567890", "abcdefghij", "+14155552671"]:
        try:
            validate_indian_mobile(invalid)
            assert False, f"Expected validation failure for '{invalid}'"
        except ValueError:
            pass
    print("[PASS] 10-digit Indian mobile validation verified.")

    # 2. Test Product Catalog Lookup
    print("\n[TEST 2] Product Catalog Lookup & Normalization...")
    prod101 = catalog.get_product("PROD101")
    assert prod101 is not None
    assert prod101["code"] == "PROD101"
    assert "Karungali" in prod101["name"] or "கருங்காலி" in prod101["name"]
    assert prod101["offer_price"] > 0
    assert prod101["mrp"] >= prod101["offer_price"]

    prod10 = catalog.get_product("10")
    assert prod10 is not None
    assert prod10["offer_price"] == 1100.0
    print(f"[PASS] Product lookup verified: '{prod101['name']}' (₹{prod101['offer_price']}) and '{prod10['name']}' (₹{prod10['offer_price']}).")

    # 3. Test Pluggable Telephony Provider
    print("\n[TEST 3] Pluggable Telephony Provider...")
    sim_provider = telephony.get_telephony_provider("simulated")
    assert sim_provider.is_configured() is True
    call_init = sim_provider.initiate_call("9876543210", "CALL_001", "ta", prod101)
    assert call_init["success"] is True
    assert call_init["is_simulated"] is True
    print("[PASS] Simulated development telephony provider verified.")

    # 4. Test Tamil Calling Conversation Flow & Positive Intent
    print("\n[TEST 4] Tamil Dialogue Flow & Explicit Interest Confirmation...")
    engine_ta = LeadConversationEngine(
        call_id="CALL_TEST_TA",
        mobile="9876543210",
        proid="PROD101",
        language="ta",
        product_info=prod101
    )

    greeting_ta = engine_ta.get_initial_greeting()
    assert "வணக்கம்" in greeting_ta
    assert "நித்ரா" in greeting_ta
    assert ("ஸ்ரீ தியா" in greeting_ta or "AI உதவியாளர்" in greeting_ta)
    assert prod101["name"] in greeting_ta
    print(f"  AI Greeting: {greeting_ta[:60]}...")

    # Customer agrees to speak
    pitch_ta = engine_ta.get_pitch_prompt()
    assert "விருப்பம் இருக்கா" in pitch_ta
    print(f"  AI Pitch: {pitch_ta[:60]}...")

    # Customer explicitly confirms purchase interest
    turn_pos = engine_ta.process_customer_turn("ஆமாங்க, இந்த product வாங்க விருப்பம் இருக்கு")
    assert turn_pos["lead_status"] == "INTERESTED"
    assert turn_pos["is_completed"] is True
    assert ("உறுதி பண்ணிக்கிறேன்" in turn_pos["reply_text"] or "confirm" in turn_pos["reply_text"])

    # VERIFY STRICT JSON OUTPUT PAYLOAD:
    # { "mobile": "9876543210", "proid": "PROD101" }
    payload = turn_pos["order_payload"]
    assert payload is not None, "Order payload must be generated for confirmed interest!"
    assert list(payload.keys()) == ["mobile", "proid"], f"Payload must contain EXACTLY 'mobile' and 'proid', got {list(payload.keys())}"
    assert payload["mobile"] == "9876543210"
    assert payload["proid"] == "PROD101"
    print(f"[PASS] Strict JSON output verified:\n  {payload}")

    # 5. Test Telugu Calling Conversation Flow & Negative Intent
    print("\n[TEST 5] Telugu Dialogue Flow & Decline...")
    engine_te = LeadConversationEngine(
        call_id="CALL_TEST_TE",
        mobile="9123456789",
        proid="10",
        language="te",
        product_info=prod10
    )

    greeting_te = engine_te.get_initial_greeting()
    assert "నమస్కారం" in greeting_te
    assert ("శ్రీ దియా" in greeting_te or "AI అసిస్టెంట్" in greeting_te)
    assert prod10["name"] in greeting_te
    print(f"  AI Greeting: {greeting_te[:60]}...")

    pitch_te = engine_te.get_pitch_prompt()
    assert "ఆసక్తి ఉందా" in pitch_te

    # Customer declines
    turn_neg = engine_te.process_customer_turn("వద్దు, నాకు ఆసక్తి లేదు")
    assert turn_neg["lead_status"] == "NOT_INTERESTED"
    assert turn_neg["is_completed"] is True
    assert "సరే" in turn_neg["reply_text"]
    # STRICT REQUIREMENT: For non-interested conversations, do not generate an order payload!
    assert turn_neg["order_payload"] is None
    print("[PASS] Telugu decline flow verified (order_payload is None for NOT_INTERESTED).")

    # 6. Test Callback Request & Do Not Call Intent
    print("\n[TEST 6] Callback Request & Do Not Call Handling...")
    engine_cb = LeadConversationEngine("CALL_CB", "9876543210", "PROD101", "ta", prod101)
    res_cb = engine_cb.process_customer_turn("இப்போ busy, அப்புறம் கூப்பிடுங்க")
    assert res_cb["lead_status"] == "CALLBACK_REQUESTED"
    assert res_cb["order_payload"] is None

    # Tanglish callback directly after greeting ("aprum kupitu", "aprum kupdunga")
    engine_cb2 = LeadConversationEngine("CALL_CB2", "9876543210", "PROD101", "ta", prod101)
    engine_cb2.get_initial_greeting()
    res_cb2 = engine_cb2.process_customer_turn("aprum kupitu")
    assert res_cb2["lead_status"] == "CALLBACK_REQUESTED"
    assert res_cb2["is_completed"] is True
    assert res_cb2["order_payload"] is None
    assert "சரிங்க" in res_cb2["reply_text"]
    assert "விலை" not in res_cb2["reply_text"]  # MUST NOT PITCH PRODUCT

    engine_cb3 = LeadConversationEngine("CALL_CB3", "9876543210", "PROD101", "ta", prod101)
    engine_cb3.get_initial_greeting()
    res_cb3 = engine_cb3.process_customer_turn("aprum kupdunga")
    assert res_cb3["lead_status"] == "CALLBACK_REQUESTED"
    assert res_cb3["is_completed"] is True
    assert res_cb3["order_payload"] is None

    engine_dnc = LeadConversationEngine("CALL_DNC", "9876543210", "PROD101", "ta", prod101)
    res_dnc = engine_dnc.process_customer_turn("இனிமேல் கால் பண்ணாதீங்க, remove my number")
    assert res_dnc["lead_status"] == "DO_NOT_CALL"
    assert res_dnc["order_payload"] is None
    print("[PASS] Callback & Do-Not-Call intents correctly detected without order payload.")

    # 7. Test Language Switching
    print("\n[TEST 7] Dynamic Language Switching...")
    assert detect_language_switch_request("தெலுங்குல பேசுங்க", "ta") == "te"
    assert detect_language_switch_request("please speak in Telugu", "ta") == "te"
    assert detect_language_switch_request("தமிழ்ல பேசுங்க", "te") == "ta"
    print("[PASS] Code-switching and language switching heuristics verified.")

    # 8. Test Database Operations & Webhook Idempotency
    print("\n[TEST 8] Database Persistence & Webhook Idempotency...")
    import uuid
    db_test_id = f"CALL_DB_{uuid.uuid4().hex[:8]}"
    call_rec = database.create_call(
        call_id=db_test_id,
        mobile="9876543210",
        proid="PROD101",
        language="ta",
        is_simulated=True,
        product_snapshot=prod101
    )
    assert call_rec["call_id"] == db_test_id
    assert call_rec["status"] == "INITIATED"

    database.add_transcript(db_test_id, "AI", "வணக்கம்!")
    database.add_transcript(db_test_id, "CUSTOMER", "சொல்லுங்க")
    trans = database.get_call_transcript(db_test_id)
    assert len(trans) == 2
    assert trans[0]["speaker"] == "AI"

    # Update call with confirmed interest order payload
    database.update_call_status(
        call_id=db_test_id,
        status="COMPLETED",
        lead_status="INTERESTED",
        order_payload={"mobile": "9876543210", "proid": "PROD101"}
    )
    saved_call = database.get_call(db_test_id)
    assert saved_call["status"] == "COMPLETED"
    assert saved_call["lead_status"] == "INTERESTED"
    assert saved_call["order_payload"] == {"mobile": "9876543210", "proid": "PROD101"}

    # Webhook idempotency test
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    assert database.is_event_processed(event_id) is False
    database.record_webhook_event(event_id, db_test_id, "COMPLETED", {"status": "ok"})
    assert database.is_event_processed(event_id) is True
    print("[PASS] Database operations and webhook idempotency verified.")

    # -------------------------------------------------------------
    # 9. Strict Scope & Out-of-Scope Question Handling
    # -------------------------------------------------------------
    print("\n[TEST 9] Strict Nithra - sridiya Scope & Out-of-Scope Redirection...")
    engine_scope_ta = LeadConversationEngine(
        call_id="CALL_SCOPE_TA",
        mobile="9876543210",
        proid="PROD101",
        language="ta",
        product_info={"name": "கருங்காலி மாலை", "mrp": 1500, "offer_price": 1300}
    )
    # Unrelated personal / general knowledge questions
    res1 = engine_scope_ta.process_customer_turn("இன்னைக்கு மழை வருமா? weather சொல்லுங்க")
    assert "நித்ரா - ஸ்ரீதியா" in res1["reply_text"] or "Nithra - sridiya" in res1["reply_text"]
    assert res1["lead_status"] == "UNDECIDED"
    assert res1["is_completed"] is False
    assert res1["order_payload"] is None

    res2 = engine_scope_ta.process_customer_turn("உங்களுக்கு கல்யாணம் ஆயிடுச்சா?")
    assert "நித்ரா - ஸ்ரீதியா" in res2["reply_text"] or "Nithra - sridiya" in res2["reply_text"]
    assert res2["lead_status"] == "UNDECIDED"
    assert res2["is_completed"] is False

    # Telugu out-of-scope question
    engine_scope_te = LeadConversationEngine(
        call_id="CALL_SCOPE_TE",
        mobile="9123456789",
        proid="PROD101",
        language="te",
        product_info={"name": "నల్లమద్ది కర్ర", "mrp": 1500, "offer_price": 1100}
    )
    res3 = engine_scope_te.process_customer_turn("who is the prime minister of india?")
    assert "నిత్రా - శ్రీదియా" in res3["reply_text"] or "Nithra - sridiya" in res3["reply_text"]
    assert res3["lead_status"] == "UNDECIDED"
    assert res3["is_completed"] is False
    print("[PASS] Strict Nithra - sridiya scope verified: unrelated questions politely declined and redirected.")

    print("\n==================================================")
    print("ALL 9 VERIFICATION SUITES PASSED FLAWLESSLY! [OK]")
    print("==================================================")



if __name__ == "__main__":
    run_all_tests()
