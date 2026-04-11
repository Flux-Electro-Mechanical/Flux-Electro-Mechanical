# FLUX Deployment Package

## Included
- requirements.txt
- Procfile
- runtime.txt
- .env.example
- railway.json
- render.yaml

## Railway
1. Create a new Railway project.
2. Upload this folder or connect the GitHub repo.
3. Add a PostgreSQL service.
4. Set variables:
   - DATABASE_URL
   - FLASK_SECRET_KEY
   - COOKIE_SECURE=true
5. Deploy.

## Render
1. Create a new Web Service from this repo.
2. Use render.yaml or set manually:
   - Build Command: pip install -r requirements.txt
   - Start Command: gunicorn app:app
3. Add PostgreSQL.
4. Set:
   - DATABASE_URL
   - FLASK_SECRET_KEY
   - COOKIE_SECURE=true

## Local test
PowerShell:
$env:DATABASE_URL="postgresql://postgres:password@localhost:5432/fluxdb"
$env:FLASK_SECRET_KEY="replace-this"
python app.py

## Notes
- Use PostgreSQL in production.
- Set COOKIE_SECURE=true in production.
- Change FLASK_SECRET_KEY before deployment.
- If uploads are important long term, move them later to cloud storage.

## Recommended next production upgrade
- PostgreSQL-only cleanup
- real migrations
- logging
- backup plan
- cloud file storage
