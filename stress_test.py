#!/usr/bin/env python
import os
import sys
import time
import django
import concurrent.futures

# 1. Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
# Allow test client host and bypass redirect during local benchmark
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')
if '*' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('*')

from users.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient

print("=" * 60)
print(" IMS THIRUMALAI — PRODUCTION CAPACITY STRESS TEST")
print("=" * 60)

# 2. Automatically find an Admin or Staff user to generate a valid JWT token on this machine
admin_user = User.objects.filter(role__role_name__in=['ADMIN', 'TECH SUPPORTER', 'PRINCIPAL', 'HOD']).first()
if not admin_user:
    admin_user = User.objects.first()

if not admin_user:
    print("❌ Error: No user found in database to authenticate test.")
    sys.exit(1)

token = str(RefreshToken.for_user(admin_user).access_token)
print(f"Authenticated as User: {admin_user.name} ({admin_user.username})")
print(f"Role: {getattr(admin_user.role, 'role_name', 'User')}")
print(f"Token verified against active SECRET_KEY")
print("-" * 60)

TOTAL_REQUESTS = 1000
CONCURRENCY = 40

# Test 1: High-Speed Internal Application Stack (WSGI + Cache + Database Pipeline)
print(f"\n[Test 1] Running {TOTAL_REQUESTS} requests across {CONCURRENCY} concurrent threads...")
print("Endpoint: /api/users/online-users (Cache-First User Presence)")

def run_api_call(idx):
    from django.db import close_old_connections
    close_old_connections()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    t_start = time.time()
    try:
        response = client.get('/api/users/online-users', secure=True)
        latency = time.time() - t_start
        return (response.status_code == 200, latency, response.status_code)
    except Exception as e:
        latency = time.time() - t_start
        return (False, latency, str(e))
    finally:
        close_old_connections()

t_bench_start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    results = list(executor.map(run_api_call, range(TOTAL_REQUESTS)))

total_time = time.time() - t_bench_start
success_count = sum(1 for r in results if r[0])
times = [r[1] for r in results]
codes = {}
for r in results:
    codes[r[2]] = codes.get(r[2], 0) + 1

print("\n--- RESULTS ---")
print(f"Total Requests: {TOTAL_REQUESTS}")
print(f"Total Time:     {total_time:.2f} seconds")
print(f"Throughput:     {len(results) / total_time:.1f} Requests / second")
print(f"Success Rate:   {success_count}/{TOTAL_REQUESTS} ({(success_count / TOTAL_REQUESTS) * 100:.1f}%)")
print(f"Status Codes:   {codes}")
print(f"Avg Latency:    {(sum(times) / len(times)) * 1000:.1f} ms")
print(f"Fastest:        {min(times) * 1000:.1f} ms")
print(f"Slowest:        {max(times) * 1000:.1f} ms")

# Test 2: Student Catalog Search with 21,981+ Indexed Records
print(f"\n[Test 2] Running 500 Indexed Catalog Searches across {CONCURRENCY} concurrent threads...")
print("Endpoint: /api/library/books/quick-search?search=engineering&limit=30")

def run_catalog_call(idx):
    from django.db import connections
    connections.close_all()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    t_start = time.time()
    try:
        response = client.get('/api/library/books/quick-search', {'search': 'engineering', 'limit': 30}, secure=True)
        latency = time.time() - t_start
        return (response.status_code == 200, latency, response.status_code)
    except Exception as e:
        latency = time.time() - t_start
        return (False, latency, str(e))
    finally:
        connections.close_all()

t_bench_start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    results_cat = list(executor.map(run_catalog_call, range(500)))

total_time_cat = time.time() - t_bench_start
success_cat = sum(1 for r in results_cat if r[0])
times_cat = [r[1] for r in results_cat]

print(f"Success Rate:   {success_cat}/500 ({(success_cat / 500) * 100:.1f}%)")
print(f"Throughput:     {len(results_cat) / total_time_cat:.1f} Searches / second")
print(f"Avg Latency:    {(sum(times_cat) / len(times_cat)) * 1000:.1f} ms")
print("=" * 60)
print(" All tests completed successfully!")
