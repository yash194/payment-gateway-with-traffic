"""
Heavy Traffic Simulator - Causes Visible OTP Failures
======================================================

Run this while using the frontend to see OTP failures!
"""
import asyncio
import aiohttp
import random
import sys
from datetime import datetime


async def make_payment(session: aiohttp.ClientSession, base_url: str):
    """Make a single payment request"""
    payload = {
        "card_number": "4111111111111111",
        "expiry": "12/25",
        "cvv": "123",
        "holder_name": f"Bot User {random.randint(1, 1000)}",
        "amount": random.uniform(10.0, 500.0),
    }
    
    try:
        async with session.post(
            f"{base_url}/payment/initiate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            result = await response.json()
            return result.get("success", False)
    except:
        return False


async def continuous_traffic(session: aiohttp.ClientSession, base_url: str, stats: dict):
    """Generate continuous traffic"""
    while True:
        success = await make_payment(session, base_url)
        stats["total"] += 1
        if success:
            stats["success"] += 1
        else:
            stats["failed"] += 1
        
        # Very short delay to maintain high concurrency
        await asyncio.sleep(random.uniform(0.05, 0.2))


async def run_simulator(base_url: str = "http://54.236.22.165:8000", workers: int = 30):
    """
    Run continuous heavy traffic.
    More workers = more contention = more OTP failures
    """
    print("=" * 60)
    print("� HEAVY TRAFFIC SIMULATOR")
    print("=" * 60)
    print(f"Target: {base_url}")
    print(f"Concurrent workers: {workers}")
    print()
    print("NOW GO TO http://localhost:3000 AND TRY TO PAY!")
    print("You should see 'Unable to generate OTP' errors!")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    stats = {"total": 0, "success": 0, "failed": 0}
    
    async with aiohttp.ClientSession() as session:
        # Start worker tasks
        tasks = [
            asyncio.create_task(continuous_traffic(session, base_url, stats))
            for _ in range(workers)
        ]
        
        # Print stats every 2 seconds
        try:
            while True:
                await asyncio.sleep(2)
                rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                status = "✅" if rate >= 95 else "⚠️" if rate >= 80 else "❌"
                print(f"[{timestamp}] {status} Total: {stats['total']:>5} | Success: {stats['success']:>5} | Failed: {stats['failed']:>4} | Rate: {rate:.1f}%")
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()


def main():
    base_url = "http://54.236.22.165:8000"
    workers = 30  # 30 concurrent workers hammering the system
    
    if len(sys.argv) > 1:
        workers = int(sys.argv[1])
    
    try:
        asyncio.run(run_simulator(base_url, workers))
    except KeyboardInterrupt:
        print("\n\nTraffic stopped.")


if __name__ == "__main__":
    main()
