# Deploying the chatbot (text-to-SQL agent) to an Oracle Cloud instance

This covers `chatbot_deploy.zip` - a self-contained copy of the `agent/`
folder plus the cleaned data it needs to build its own local database.

1. Copy `chatbot_deploy.zip` to the instance (scp/rsync/etc.) and unzip it,
   e.g. into `/opt/upi-agent/`.
2. Install Python 3.10+ and pip if not already present.
3. `pip install -r requirements.txt`
4. Build the local database from the bundled cleaned CSVs:
   `python3 agent/build_db.py`
   (reads `data/cleaned/*.csv` -> writes `agent/analytics.db`)
5. Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY` if you want
   the LLM fallback for open-ended questions. This is optional - the ~21
   local SQL templates work fully offline without it.
6. Start the API, bound to all interfaces so it's reachable from outside the
   instance:
   `python3 -m uvicorn agent.app:app --host 0.0.0.0 --port 8000`
   Open port 8000 in the instance's Oracle Cloud security list / network
   security group (and in the OS firewall, e.g. `firewalld`/`ufw`, if enabled).
7. (Optional) Run the Streamlit UI the same way:
   `python3 -m streamlit run agent/frontend.py --server.address 0.0.0.0 --server.port 8501`
8. If a web page hosted elsewhere (e.g. the dashboard embed page) will call
   this API's `/ask` endpoint from the browser, make sure CORS is enabled
   for that page's origin in `agent/app.py` (see the `CORSMiddleware` there).
9. For production use behind a real domain, put this behind a reverse proxy
   (nginx/Caddy) with TLS rather than exposing uvicorn directly on the public
   internet - the app itself has no authentication of its own, only a
   read-only SQL guardrail (`agent/safety.py`).

Keep `.env` off the instance's version control and out of the zip you send
anywhere else - it's excluded from `chatbot_deploy.zip` on purpose.
