# AI Assisted Project App

Flask backend for refining user‐uploaded images and generating project breakdowns via Google Vertex AI (Gemini). Powered with Google tools including Buckets, Cloud SQL, and Cloud Run. 

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask run
