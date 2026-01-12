"""
OTP Service for Payment Gateway
Handles OTP generation with strict timeout requirements
"""
import random
import string
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

from config import OTP_EXPIRY_MINUTES, OTP_TIMEOUT_MS
import database


def generate_otp_code() -> str:
    """Generate a random 6-digit OTP code"""
    return "".join(random.choices(string.digits, k=6))


def generate_session_id() -> str:
    """Generate a unique session ID"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=16))


def create_otp_for_payment(payment_intent_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Generate OTP for a payment intent.
    
    CRITICAL: This function has a strict timeout (OTP_TIMEOUT_MS).
    It waits for the payment intent to be in a valid state before generating OTP.
    
    This creates a HIDDEN DEPENDENCY:
    - If payment creation takes too long, this times out
    - The timeout is silent (no crash, no loud error)
    - Caller receives None values indicating failure
    
    Returns:
        Tuple of (session_id, otp_code, error_message)
        - On success: (session_id, otp_code, None)
        - On timeout: (None, None, None) - SILENT FAILURE
        - On error: (None, None, error_message)
    """
    start_time = time.time()
    
    # Wait for payment intent to be ready
    # This polls the database with the configured timeout
    payment = database.get_payment_intent(payment_intent_id, timeout_ms=OTP_TIMEOUT_MS)
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    if payment is None:
        # Timeout or not found - SILENT FAILURE
        # This is the critical failure point that's hard to debug
        return None, None, None
    
    # Check if we still have time to complete
    remaining_ms = OTP_TIMEOUT_MS - elapsed_ms
    if remaining_ms < 50:  # Need at least 50ms to create OTP session
        return None, None, None
    
    # Generate OTP
    session_id = generate_session_id()
    otp_code = generate_otp_code()
    expiry_time = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    try:
        database.create_otp_session(
            payment_intent_id=payment_intent_id,
            otp_code=otp_code,
            expiry_time=expiry_time
        )
        return session_id, otp_code, None
    except Exception as e:
        return None, None, str(e)


def verify_otp(session_id: str, otp_code: str) -> Tuple[bool, str]:
    """
    Verify an OTP code for a session.
    
    Returns:
        Tuple of (success, message)
    """
    session = database.get_otp_session(session_id)
    
    if not session:
        return False, "Invalid or expired session"
    
    if session.get("verified"):
        return False, "OTP already used"
    
    if datetime.utcnow() > session["expires_at"]:
        database.verify_otp_session(session_id, success=False)
        return False, "OTP has expired"
    
    if session["otp"] != otp_code:
        database.verify_otp_session(session_id, success=False)
        return False, "Invalid OTP"
    
    database.verify_otp_session(session_id, success=True)
    return True, "Payment verified successfully"
