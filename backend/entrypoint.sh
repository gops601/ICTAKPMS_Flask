#!/bin/sh
set -e

echo "Applying database migrations..."
flask db upgrade

echo "Seeding reference data..."
flask seed

if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  flask create-admin
fi

echo "Syncing domain data..."
flask sync-data || echo "sync-data reported a problem (continuing)"

exec gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 --access-logfile - run:app
