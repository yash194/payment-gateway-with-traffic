"""
Load Generator for Payment Gateway
Simulates realistic traffic to demonstrate failure modes
"""
import asyncio
import aiohttp
import time
import random
from dataclasses import dataclass
from typing import List
import statistics


@dataclass
class LoadTestResult:
    """Results from a load test run"""
    total_requests: int
    successful_payments: int
    failed_otp_generation: int
    other_failures: int
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    otp_success_rate: float
    
    def __str__(self):
        return f"""
╔════════════════════════════════════════════╗
║         LOAD TEST RESULTS                  ║
╠════════════════════════════════════════════╣
║ Total Requests:        {self.total_requests:>8}             ║
║ Successful Payments:   {self.successful_payments:>8}             ║
║ Failed OTP Generation: {self.failed_otp_generation:>8}             ║
║ Other Failures:        {self.other_failures:>8}             ║
╠════════════════════════════════════════════╣
║ OTP Success Rate:      {self.otp_success_rate:>7.1f}%            ║
║ Avg Latency:           {self.avg_latency_ms:>7.1f}ms           ║
║ P95 Latency:           {self.p95_latency_ms:>7.1f}ms           ║
║ P99 Latency:           {self.p99_latency_ms:>7.1f}ms           ║
╚════════════════════════════════════════════╝
"""


async def make_payment_request(
    session: aiohttp.ClientSession,
    base_url: str,
    request_id: int
) -> dict:
    """Make a single payment request and track result"""
    start_time = time.time()
    
    payload = {
        "card_number": f"4111111111111111",
        "expiry": "12/25",
        "cvv": "123",
        "holder_name": f"Test User {request_id}",
        "amount": random.uniform(10.0, 1000.0),
        "currency": "USD",
        "merchant_id": f"merchant_{request_id % 10}"
    }
    
    try:
        async with session.post(
            f"{base_url}/payment/initiate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            result = await response.json()
            latency_ms = (time.time() - start_time) * 1000
            
            return {
                "success": result.get("success", False),
                "otp_generated": result.get("otp") is not None,
                "latency_ms": latency_ms,
                "message": result.get("message", "")
            }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "otp_generated": False,
            "latency_ms": latency_ms,
            "message": str(e)
        }


async def run_load_test(
    base_url: str = "http://localhost:8000",
    total_requests: int = 100,
    concurrency: int = 20,
    burst_enabled: bool = True
) -> LoadTestResult:
    """
    Run a load test against the payment gateway.
    
    Args:
        base_url: Base URL of the payment gateway
        total_requests: Total number of requests to make
        concurrency: Number of concurrent requests
        burst_enabled: If True, traffic will have bursty patterns
    
    Returns:
        LoadTestResult with statistics
    """
    print(f"\n🚀 Starting load test: {total_requests} requests, {concurrency} concurrent")
    
    results: List[dict] = []
    
    async with aiohttp.ClientSession() as session:
        # Create batches of requests
        batches = []
        for i in range(0, total_requests, concurrency):
            batch_size = min(concurrency, total_requests - i)
            
            # Add burstiness - some batches have higher concurrency
            if burst_enabled and random.random() < 0.3:
                batch_size = min(batch_size * 2, total_requests - i)
            
            batches.append((i, batch_size))
        
        for batch_start, batch_size in batches:
            # Create concurrent requests for this batch
            tasks = [
                make_payment_request(session, base_url, batch_start + j)
                for j in range(batch_size)
            ]
            
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            
            # Small delay between batches
            if burst_enabled:
                await asyncio.sleep(random.uniform(0.01, 0.1))
            else:
                await asyncio.sleep(0.05)
            
            # Progress indicator
            print(f"  Progress: {len(results)}/{total_requests}", end="\r")
    
    print()  # New line after progress
    
    # Calculate statistics
    successful = sum(1 for r in results if r["success"])
    otp_failed = sum(1 for r in results if not r["otp_generated"] and "OTP" in r.get("message", ""))
    other_failed = sum(1 for r in results if not r["success"] and "OTP" not in r.get("message", ""))
    
    latencies = [r["latency_ms"] for r in results]
    latencies.sort()
    
    return LoadTestResult(
        total_requests=len(results),
        successful_payments=successful,
        failed_otp_generation=otp_failed,
        other_failures=other_failed,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        p95_latency_ms=latencies[int(len(latencies) * 0.95)] if latencies else 0,
        p99_latency_ms=latencies[int(len(latencies) * 0.99)] if latencies else 0,
        otp_success_rate=(successful / len(results) * 100) if results else 0
    )


async def main():
    """Run the load test demo"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Payment Gateway Load Test")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--requests", type=int, default=100, help="Total requests")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent requests")
    parser.add_argument("--no-burst", action="store_true", help="Disable bursty traffic")
    
    args = parser.parse_args()
    
    result = await run_load_test(
        base_url=args.url,
        total_requests=args.requests,
        concurrency=args.concurrency,
        burst_enabled=not args.no_burst
    )
    
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
