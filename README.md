# Payment Gateway Demo

A demo payment processing system with OTP verification, designed to demonstrate how subtle database changes can cause cascading failures under load.

## Architecture

```
┌─────────────┐     ┌─────────────────────────────────────────────┐     ┌─────────────┐
│   React     │────▶│              FastAPI Backend                │────▶│   MongoDB   │
│  Frontend   │     │  ┌──────────────┐  ┌──────────────────┐     │     │  Database   │
│   :3000     │     │  │Payment       │─▶│ OTP Service      │     │     │   :27017    │
│             │     │  │Service       │  │ (400ms timeout)  │     │     │             │
└─────────────┘     │  └──────────────┘  └──────────────────┘     │     └─────────────┘
                    └─────────────────────────────────────────────┘
```

## Quick Start

```bash
# Start all services
docker-compose up --build

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Testing the Flow

1. Open http://localhost:3000
2. Enter test card: `4111111111111111`, expiry: `12/25`, CVV: `123`
3. Note the OTP displayed (demo only)
4. Enter the OTP to complete payment

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/payment/initiate` | POST | Submit card details, receive OTP |
| `/payment/verify-otp` | POST | Verify OTP, get payment status |
| `/health` | GET | Health check |
| `/debug/config` | GET | View current configuration |

---

## � Switching Between Database Versions

This project includes two database implementations:

| File | Description | Performance |
|------|-------------|-------------|
| `database_original.py` | Fast, simple implementation | ~30ms per payment, 100% OTP success |
| `database_with_audit.py` | With audit logging (DANGEROUS) | ~300ms+ under load, ~80% OTP success |

### Apply the DANGEROUS Database (Causes OTP Failures)

```bash
cd backend
cp database_with_audit.py database.py
docker-compose up --build -d backend
```

### Revert to SAFE Database (100% Success)

```bash
cd backend
cp database_original.py database.py
docker-compose up --build -d backend
```

### Test with Traffic Simulator

```bash
cd backend
python traffic_simulator.py 40
```

Then open http://localhost:3000 and try to make a payment.

---

## 🔬 The Specific Database Change That Causes OTP Failures

### What Changed

The `database_with_audit.py` adds **audit logging** to the payment creation flow:

```python
# ORIGINAL (database_original.py) - Fast path
def create_payment_intent(...):
    db.payment_intents.insert_one(payment_intent)      # ~15ms
    db.payment_intents.update_one(...)                 # ~15ms
    # Total: ~30ms ✅
```

```python
# DANGEROUS (database_with_audit.py) - Slow path
def create_payment_intent(...):
    db.payment_intents.insert_one(payment_intent)      # ~15ms
    
    # AUDIT LOG #1 - Added for "compliance"
    time.sleep(0.1)  # 100ms latency
    db.audit_logs.insert_one({...})                    # Extra write
    
    db.payment_intents.update_one(...)                 # ~15ms
    
    # AUDIT LOG #2 - Added for "tracking"
    time.sleep(0.1)  # 100ms latency
    db.audit_logs.insert_one({...})                    # Extra write
    
    # Total: ~250ms+ ❌
```

### Why This Causes OTP Failures

The payment flow has a **hidden timing dependency**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PAYMENT CREATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Payment Service creates payment_intent                              │
│     ├── Insert payment_intent document                                  │
│     ├── [DANGEROUS] Write audit log #1 (+100ms)                        │
│     ├── Update status to "awaiting_otp"                                │
│     └── [DANGEROUS] Write audit log #2 (+100ms)                        │
│                                                                         │
│  2. OTP Service tries to generate OTP                                   │
│     ├── Query: find payment where status = "awaiting_otp"              │
│     ├── TIMEOUT: 400ms ⏱️                                               │
│     └── If payment not ready in 400ms → SILENT FAILURE                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**The Problem:**
- OTP Service has a **400ms timeout** waiting for the payment to be ready
- Original database: Payment ready in ~30ms → OTP succeeds ✅
- Dangerous database: Payment ready in ~250ms → Usually OK
- **Under concurrent load**: Contention adds +50ms per concurrent request
- With 10 concurrent payments: 250ms + (10 × 50ms) = **750ms > 400ms** → OTP FAILS ❌

### Contention Amplification

The `database_with_audit.py` also tracks concurrent transactions:

```python
def _get_contention_delay():
    # Each concurrent write adds 50ms delay
    return _active_writes * 50
```

| Concurrent Payments | Base Latency | Contention Delay | Total | OTP Result |
|---------------------|--------------|------------------|-------|------------|
| 1 | 250ms | 50ms | 300ms | ✅ Success |
| 3 | 250ms | 150ms | 400ms | ⚠️ Borderline |
| 5 | 250ms | 250ms | 500ms | ❌ Timeout |
| 10 | 250ms | 500ms | 750ms | ❌ Timeout |

### Why This Change Looks Safe

| Aspect | Justification | Hidden Problem |
|--------|---------------|----------------|
| Audit logging | "We need this for compliance" | Adds 200ms+ latency |
| Two audit entries | "Track creation and status change" | Doubles the overhead |
| Contention tracking | "Matches real DB behavior" | Exponential degradation |

### The Silent Failure

When OTP generation times out:
- No exception is thrown
- No error is logged
- Service health check returns "healthy"
- User sees: **"Unable to generate OTP. Please try again."**

This makes the problem extremely hard to debug without understanding the hidden timing dependency.

---

## 📊 Test Results

### With ORIGINAL Database (Safe)

```
🚀 Traffic Test: 40 concurrent workers
Total:  2,181 | Success:  2,181 | Failed:    0 | Rate: 100.0% ✅
```

### With DANGEROUS Database (Audit Logging)

```
🚀 Traffic Test: 40 concurrent workers
Total:    112 | Success:     90 | Failed:   22 | Rate: 80.4% ❌
```

---

## Project Structure

```
payment-gateway/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration (OTP timeout: 400ms)
│   ├── database.py             # Active database layer
│   ├── database_original.py    # SAFE - Fast implementation
│   ├── database_with_audit.py  # DANGEROUS - With audit logging
│   ├── otp_service.py          # OTP generation (400ms timeout)
│   ├── payment_service.py      # Payment orchestration
│   ├── traffic_simulator.py    # Load testing tool
│   ├── load_generator.py       # Batch load testing
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.js              # Main React component
│   │   └── components/         # UI components
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Key Takeaways

1. **The change looks reasonable**: Audit logging is a common compliance requirement
2. **Unit tests pass**: No concurrency in tests means no timeout issues
3. **Low traffic works fine**: Single requests complete well under 400ms
4. **Failure emerges under load**: Contention + audit latency exceeds OTP timeout
5. **Failure is silent**: No crashes, no errors, just degraded user experience

---

## Notes

⚠️ **This is a demo system only** - No real payment processing occurs. The OTP is returned in the API response for testing convenience.
