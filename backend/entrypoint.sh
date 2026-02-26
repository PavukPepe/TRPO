#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
" 2>/dev/null; do
  sleep 1
done
echo "Database is ready."

python manage.py migrate --noinput
python manage.py create_default_admin
python manage.py collectstatic --noinput

exec "$@"
