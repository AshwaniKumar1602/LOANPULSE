#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "=========================================================="
echo "==> LoanPulse Render Free-Tier Build Process Starting"
echo "=========================================================="

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Applying database migrations (Flask-Migrate / Alembic)..."
flask db upgrade

echo "==> Seeding essential initial institutional loan products..."
flask create-initial-products || true

echo "=========================================================="
echo "==> LoanPulse Build Completed Successfully!"
echo "=========================================================="
