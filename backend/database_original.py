"""
Database Layer for Payment Gateway
Handles MongoDB operations for payment intents and OTP sessions
"""
import time
import uuid
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import (
    MONGO_URI, 
    DATABASE_NAME,
    BASE_WRITE_LATENCY_MS,
    CONTENTION_FACTOR
)


_active_transactions = 0
_transaction_lock = threading.Lock()


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
    
    @property
    def client(self):
        return self._client


def get_db():
    """Get database instance"""
    return DatabaseConnection().db


def get_client():
    """Get MongoDB client (for transactions)"""
    return DatabaseConnection().client


def _simulate_write_latency():
   
    global _active_transactions
    
    with _transaction_lock:
        concurrent = _active_transactions
    
    
    latency_ms = BASE_WRITE_LATENCY_MS * (1 + concurrent * CONTENTION_FACTOR * 0.1)
    time.sleep(latency_ms / 1000.0)


def _track_transaction_start():
    """Track when a transaction starts"""
    global _active_transactions
    with _transaction_lock:
        _active_transactions += 1


def _track_transaction_end():
    """Track when a transaction ends"""
    global _active_transactions
    with _transaction_lock:
        _active_transactions = max(0, _active_transactions - 1)


def create_payment_intent(
    merchant_id: str,
    amount: float,
    currency: str,
    card_last_four: str,
    holder_name: str
) -> Dict[str, Any]:
 
    db = get_db()
    
    payment_intent = {
        "_id": str(uuid.uuid4()),
        "merchant_id": merchant_id,
        "amount": amount,
        "currency": currency,
        "card_last_four": card_last_four,
        "holder_name": holder_name,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "committed_at": None  
    }
    
    _track_transaction_start()
    try:
        _simulate_write_latency()
        db.payment_intents.insert_one(payment_intent)
        
        
        payment_intent["status"] = "awaiting_otp"
        db.payment_intents.update_one(
            {"_id": payment_intent["_id"]},
            {"$set": {"status": "awaiting_otp"}}
        )
    finally:
        _track_transaction_end()
    
    return payment_intent


def get_payment_intent(payment_id: str, timeout_ms: int = 400) -> Optional[Dict[str, Any]]:
    """
    Get a payment intent by ID.
    
    CRITICAL: This is used by OTP service and has a timeout.
    The timeout simulates real-world service timeouts.
    
    Returns None if timeout exceeded or not found.
    """
    db = get_db()
    start_time = time.time()
    
    
    while True:
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > timeout_ms:
            return None  
        
        payment = db.payment_intents.find_one({
            "_id": payment_id,
            "status": {"$in": ["awaiting_otp", "otp_sent", "completed"]}
        })
        
        if payment:
            return payment
        
        
        time.sleep(0.01)


def create_otp_session(
    payment_intent_id: str,
    otp_code: str,
    expiry_time: datetime
) -> Dict[str, Any]:
   
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
    
    # Update payment intent status
    db.payment_intents.update_one(
        {"_id": payment_intent_id},
        {"$set": {"status": "otp_sent"}}
    )
    
    return session


def get_otp_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get OTP session by ID"""
    db = get_db()
    return db.otp_sessions.find_one({"_id": session_id})


def verify_otp_session(session_id: str, success: bool) -> bool:
    """Mark OTP session as verified or failed"""
    db = get_db()
    
    result = db.otp_sessions.update_one(
        {"_id": session_id, "verified": False},
        {"$set": {
            "verified": True,
            "failed": not success,
            "verified_at": datetime.utcnow()
        }}
    )
    
    if result.modified_count > 0 and success:
        # Get the session to find payment intent
        session = db.otp_sessions.find_one({"_id": session_id})
        if session:
            db.payment_intents.update_one(
                {"_id": session["payment_intent_id"]},
                {"$set": {
                    "status": "completed",
                    "committed_at": datetime.utcnow()
                }}
            )
    
    return result.modified_count > 0
