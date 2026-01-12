"""
Payment Service for Payment Gateway
Handles payment initiation with synchronous OTP generation
"""
import time
from typing import Dict, Any, Optional

from config import PAYMENT_RETRY_COUNT, PAYMENT_RETRY_DELAY_MS
import database
import otp_service


class PaymentResult:
    """Result of a payment operation"""
    def __init__(
        self,
        success: bool,
        message: str,
        session_id: Optional[str] = None,
        otp: Optional[str] = None,
        payment_id: Optional[str] = None
    ):
        self.success = success
        self.message = message
        self.session_id = session_id
        self.otp = otp
        self.payment_id = payment_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "session_id": self.session_id,
            "otp": self.otp,
            "payment_id": self.payment_id
        }


def initiate_payment(
    merchant_id: str,
    card_number: str,
    expiry: str,
    cvv: str,
    holder_name: str,
    amount: float,
    currency: str = "USD"
) -> PaymentResult:
    """
    Initiate a payment with OTP verification.
    
    Flow:
    1. Create payment intent in database
    2. SYNCHRONOUSLY call OTP service to generate OTP
    3. Return result
    
    CRITICAL: Step 2 has a timeout. If step 1 is slow, step 2 fails.
    This is the hidden coupling that can cause failures.
    
    The retry logic can amplify failures under load:
    - If OTP generation times out, we retry
    - Retries add more load to the database
    - More load = slower payment creation
    - Slower creation = more timeouts
    - More timeouts = more retries (amplification loop)
    """
    # Validate card (basic)
    card_last_four = card_number[-4:]
    
    # Step 1: Create payment intent
    try:
        payment = database.create_payment_intent(
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            card_last_four=card_last_four,
            holder_name=holder_name
        )
    except Exception as e:
        return PaymentResult(
            success=False,
            message=f"Payment creation failed: {str(e)}"
        )
    
    # Step 2: Generate OTP (with retries)
    # This is where the hidden dependency manifests
    session_id = None
    otp_code = None
    last_error = None
    
    for attempt in range(PAYMENT_RETRY_COUNT):
        session_id, otp_code, error = otp_service.create_otp_for_payment(
            payment["_id"]
        )
        
        if session_id and otp_code:
            # Success!
            break
        
        if error:
            last_error = error
        
        # If OTP generation failed (timeout), retry after delay
        # WARNING: This retry logic amplifies load under contention
        if attempt < PAYMENT_RETRY_COUNT - 1:
            time.sleep(PAYMENT_RETRY_DELAY_MS / 1000.0)
    
    if not session_id or not otp_code:
        # OTP generation failed after all retries
        # This failure is SILENT - no crash, just degraded service
        return PaymentResult(
            success=False,
            message="Unable to generate OTP. Please try again.",
            payment_id=payment["_id"]
        )
    
    return PaymentResult(
        success=True,
        message="OTP generated successfully",
        session_id=session_id,
        otp=otp_code,  # Returned for demo purposes
        payment_id=payment["_id"]
    )


def verify_payment(session_id: str, otp_code: str) -> PaymentResult:
    """
    Verify payment with OTP.
    """
    success, message = otp_service.verify_otp(session_id, otp_code)
    
    return PaymentResult(
        success=success,
        message=message,
        session_id=session_id
    )
