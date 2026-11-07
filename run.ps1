# run.ps1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Start-Process powershell -ArgumentList "uvicorn backend.main:app --reload --port 8000"
Set-Location frontend
npm install
npm run dev