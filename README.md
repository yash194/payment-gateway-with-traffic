# Payment Gateway Demo

A demo payment processing system with OTP verification built with React, FastAPI, and MongoDB.

## Architecture

```
┌─────────────┐     ┌─────────────────────────────────────────────┐     ┌─────────────┐
│   React     │────▶│              FastAPI Backend                │────▶│   MongoDB   │
│  Frontend   │     │  ┌──────────────┐  ┌──────────────────┐     │     │  Database   │
│   :3000     │     │  │Payment       │─▶│ OTP Service      │     │     │   :27017    │
│             │     │  │Service       │  │                  │     │     │             │
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

## Switching Between Database Versions

This project includes two database implementations:

| File | Description |
|------|-------------|
| `database_original.py` | Simple, fast implementation |
| `database_with_audit.py` | With audit logging for compliance |

### Switch to Audit Logging Database

```bash
cd backend
cp database_with_audit.py database.py
docker-compose up --build -d backend
```

### Switch to Original Database

```bash
cd backend
cp database_original.py database.py
docker-compose up --build -d backend
```

### Load Testing

Run the traffic simulator to test performance under load:

```bash
cd backend
python traffic_simulator.py 40
```

---

## Project Structure

```
payment-gateway/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration settings
│   ├── database.py             # Active database layer
│   ├── database_original.py    # Simple database implementation
│   ├── database_with_audit.py  # Database with audit logging
│   ├── otp_service.py          # OTP generation service
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

## Notes

⚠️ **This is a demo system only** - No real payment processing occurs. The OTP is returned in the API response for testing convenience.
