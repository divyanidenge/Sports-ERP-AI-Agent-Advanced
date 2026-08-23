import sys
from pathlib import Path

# Ensure root directory and backend directory are in sys.path
backend_dir = Path(__file__).resolve().parent
parent_dir = backend_dir.parent
for p in [str(backend_dir), str(parent_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
