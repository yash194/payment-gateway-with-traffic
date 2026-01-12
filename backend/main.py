"""
Payment Gateway - FastAPI Backend
Demo payment processing with OTP verification

ARCHITECTURE:
- Payment Service: Creates payment intents, calls OTP service synchronously
- OTP Service: Generates OTPs with strict timeout (400ms)
- Database: MongoDB with payment_intents and otp_sessions collections

HIDDEN DEPENDENCY:
OTP service waits for payment intent to be in 'awaiting_otp' status.
If payment creation is slow (due to DB contention), OTP generation times out.
This timeout is SILENT - the payment appears to fail with a generic error.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from dotenv import load_dotenv

import payment_service
import otp_service

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Payment Gateway",
    description="Demo payment processing with OTP verification",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= Request/Response Models =============

class PaymentInitiateRequest(BaseModel):
    """Request for initiating a payment"""
    card_number: str
    expiry: str
    cvv: str
    holder_name: str
    amount: float = 100.00
    currency: str = "USD"
    merchant_id: str = "demo_merchant"
    
    @validator("card_number")
    def validate_card_number(cls, v):
        cleaned = v.replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("Card number must contain only digits")
        if not (13 <= len(cleaned) <= 19):
            raise ValueError("Card number must be 13-19 digits")
        return cleaned
    
    @validator("expiry")
    def validate_expiry(cls, v):
        if "/" not in v:
            raise ValueError("Expiry must be in MM/YY format")
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError("Expiry must be in MM/YY format")
        month, year = parts
        if not (month.isdigit() and year.isdigit()):
            raise ValueError("Expiry must contain only digits")
        if not (1 <= int(month) <= 12):
            raise ValueError("Month must be between 01 and 12")
        return v
    
    @validator("cvv")
    def validate_cvv(cls, v):
        if not v.isdigit():
            raise ValueError("CVV must contain only digits")
        if not (3 <= len(v) <= 4):
            raise ValueError("CVV must be 3-4 digits")
        return v


class PaymentInitiateResponse(BaseModel):
    """Response after payment initiation"""
    success: bool
    message: str
    session_id: Optional[str] = None
    otp: Optional[str] = None  # For demo only
    payment_id: Optional[str] = None


class OTPVerifyRequest(BaseModel):
    """Request for OTP verification"""
    session_id: str
    otp: str


class OTPVerifyResponse(BaseModel):
    """Response after OTP verification"""
    success: bool
    status: str
    message: str


# ============= API Endpoints =============

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Payment Gateway",
        "version": "2.0.0"
    }


@app.get("/health")
async def health_check():
    """
    Detailed health check.
    
    NOTE: This endpoint will show healthy even when OTP 
    generation is failing due to timeouts. This is realistic -
    the service isn't crashing, it's just degraded.
    """
    return {
        "status": "healthy",
        "database": "connected",
        "otp_service": "ready"
    }


@app.post("/payment/initiate", response_model=PaymentInitiateResponse)
async def initiate_payment(request: PaymentInitiateRequest):
    """
    Initiate a payment with OTP verification.
    
    Flow:
    1. Validate card details
    2. Create payment intent in database
    3. Generate OTP (with timeout)
    4. Return OTP for demo purposes
    
    FAILURE MODE:
    If there's high DB load/contention, step 2 may take longer
    than the OTP service timeout (400ms), causing OTP generation
    to fail silently. The response will show success=False with
    a generic "Unable to generate OTP" message.
    """
    result = payment_service.initiate_payment(
        merchant_id=request.merchant_id,
        card_number=request.card_number,
        expiry=request.expiry,
        cvv=request.cvv,
        holder_name=request.holder_name,
        amount=request.amount,
        currency=request.currency
    )
    
    return PaymentInitiateResponse(
        success=result.success,
        message=result.message,
        session_id=result.session_id,
        otp=result.otp,
        payment_id=result.payment_id
    )


@app.post("/payment/verify-otp", response_model=OTPVerifyResponse)
async def verify_otp(request: OTPVerifyRequest):
    """
    Verify the OTP for a payment session.
    
    - Checks if session exists and OTP matches
    - Validates OTP hasn't expired
    - Returns payment_success or payment_failed
    """
    result = payment_service.verify_payment(
        session_id=request.session_id,
        otp_code=request.otp
    )
    
    return OTPVerifyResponse(
        success=result.success,
        status="payment_success" if result.success else "payment_failed",
        message=result.message
    )


# ============= Debug Endpoints (for demonstration) =============

@app.get("/debug/config")
async def get_config():
    """Get current configuration (for debugging)"""
    from config import (
        OTP_TIMEOUT_MS, 
        PAYMENT_RETRY_COUNT,
        BASE_WRITE_LATENCY_MS,
        CONTENTION_FACTOR
    )
    return {
        "otp_timeout_ms": OTP_TIMEOUT_MS,
        "payment_retry_count": PAYMENT_RETRY_COUNT,
        "base_write_latency_ms": BASE_WRITE_LATENCY_MS,
        "contention_factor": CONTENTION_FACTOR
    }


# Run with: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
