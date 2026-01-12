"""
Configuration for Payment Gateway Demo
"""
import os

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
DATABASE_NAME = "payment_db"

# OTP Configuration
OTP_EXPIRY_MINUTES = 2
OTP_TIMEOUT_MS = 400  # OTP service timeout in milliseconds

# Payment Configuration  
PAYMENT_RETRY_COUNT = 3
PAYMENT_RETRY_DELAY_MS = 100

# Simulated latencies (for realistic behavior)
BASE_WRITE_LATENCY_MS = 15  # Base DB write latency
CONTENTION_FACTOR = 1.5  # How much contention increases latency per concurrent txn
