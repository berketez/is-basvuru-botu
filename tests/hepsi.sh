#!/usr/bin/env bash
# Tüm testler. Ağ gerektirenler önbellekten çalışır.
set -e
cd "$(dirname "$0")/.."
echo "=== regresyon (ağ yok) ==="   && python3 tests/test_regresyon.py
echo "=== meslek kapsamı (ağ yok) ===" && python3 tests/meslek_kapsami.py
echo "=== benchmark (önbellek) ===" && python3 tests/benchmark.py
echo "=== kesinlik (önbellek) ===" && python3 tests/kesinlik.py
echo "TÜM TESTLER GEÇTİ"
