"""
Database Layer - DANGEROUS VERSION
===================================

This version simulates a problematic DB change that causes OTP failures.

The issue: Payment creation is BLOCKED while audit logs are written,
causing the OTP service (which has a 400ms timeout) to fail.
"""
import time
import uuid
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from pymongo import MongoClient

from config import MONGO_URI, DATABASE_NAME

# Global lock to simulate database contention
_db_lock = threading.Lock()
_active_writes = 0
_writes_lock = threading.Lock()


class DatabaseConnection:
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._client = MongoClient(MONGO_URI)
            cls._db = cls._client[DATABASE_NAME]
        return cls._instance
    
    @property
    def db(self):
        return self._db


def get_db():
    return DatabaseConnection().db


def _start_write():
    """Track active writes for contention simulation"""
    global _active_writes
    with _writes_lock:
        _active_writes += 1
        return _active_writes


def _end_write():
    """End write tracking"""
    global _active_writes
    with _writes_lock:
        _active_writes = max(0, _active_writes - 1)


def _get_contention_delay():
    """More concurrent writes = more delay"""
    global _active_writes
    with _writes_lock:
        # Each concurrent write adds 50ms delay
        return _active_writes * 50


def create_payment_intent(
    merchant_id: str,
    amount: float,
    currency: str,
    card_last_four: str,
    holder_name: str
) -> Dict[str, Any]:
    """
    Create payment intent with audit logging.
    
    THE PROBLEM:
    - Audit logging adds 200ms+ delay
    - Under concurrent load, delays compound
    - OTP service times out waiting for this to complete
    """
    db = get_db()
    
    payment_id = str(uuid.uuid4())
    
    payment_intent = {
        "_id": payment_id,
        "merchant_id": merchant_id,
        "amount": amount,
        "currency": currency,
        "card_last_four": card_last_four,
        "holder_name": holder_name,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "committed_at": None
    }
    
    concurrent = _start_write()
    try:
        # === THE DANGEROUS PART ===
        # Contention delay: scales with concurrent requests
        contention_delay = _get_contention_delay()
        if contention_delay > 0:
            time.sleep(contention_delay / 1000.0)
        
        # Insert payment
        db.payment_intents.insert_one(payment_intent)
        
        # Audit log #1: 100ms write
        time.sleep(0.1)
        db.audit_logs.insert_one({
            "_id": str(uuid.uuid4()),
            "payment_id": payment_id,
            "action": "created",
            "timestamp": datetime.utcnow()
        })
        
        # Update status (another DB operation)
        time.sleep(0.05)
        db.payment_intents.update_one(
            {"_id": payment_id},
            {"$set": {"status": "awaiting_otp"}}
        )
        payment_intent["status"] = "awaiting_otp"
        
        # Audit log #2: another 100ms
        time.sleep(0.1)
        db.audit_logs.insert_one({
            "_id": str(uuid.uuid4()),
            "payment_id": payment_id,
            "action": "status_changed",
            "timestamp": datetime.utcnow()
        })
        # === END DANGEROUS PART ===
        
    finally:
        _end_write()
    
    return payment_intent


def get_payment_intent(payment_id: str, timeout_ms: int = 400) -> Optional[Dict[str, Any]]:
    """
    Get payment intent with timeout.
    
    CRITICAL: Returns None if timeout exceeded!
    This causes OTP generation to fail silently.
    """
    db = get_db()
    start = time.time()
    
    while (time.time() - start) * 1000 < timeout_ms:
        payment = db.payment_intents.find_one({
            "_id": payment_id,
            "status": {"$in": ["awaiting_otp", "otp_sent", "completed"]}
        })
        if payment:
            return payment
        time.sleep(0.01)
    
    # TIMEOUT! This causes OTP failure
    return None


def create_otp_session(payment_intent_id: str, otp_code: str, expiry_time: datetime) -> Dict[str, Any]:
    db = get_db()
    
    session = {
        "_id": str(uuid.uuid4()),
        "payment_intent_id": payment_intent_id,
        "otp": otp_code,
        "created_at": datetime.utcnow(),
        "expires_at": expiry_time,
        "verified": False,
        "failed": False
    }
    
    db.otp_sessions.insert_one(session)
    db.payment_intents.update_one(
        {"_id": payment_intent_id},
        {"$set": {"status": "otp_sent"}}
    )
    
    return session


def get_otp_session(session_id: str) -> Optional[Dict[str, Any]]:
    return get_db().otp_sessions.find_one({"_id": session_id})


def verify_otp_session(session_id: str, success: bool) -> bool:
    db = get_db()
    
    result = db.otp_sessions.update_one(
        {"_id": session_id, "verified": False},
        {"$set": {"verified": True, "failed": not success, "verified_at": datetime.utcnow()}}
    )
    
    if result.modified_count > 0 and success:
        session = db.otp_sessions.find_one({"_id": session_id})
        if session:
            db.payment_intents.update_one(
                {"_id": session["payment_intent_id"]},
                {"$set": {"status": "completed", "committed_at": datetime.utcnow()}}
            )
    
    return result.modified_count > 0
