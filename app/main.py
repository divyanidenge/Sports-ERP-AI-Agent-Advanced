from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.auth_router import router as auth_router
from app.sports_router import router as sports_router
from app.agent_router import router as agent_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and seed sample data
    init_db()
    yield

app = FastAPI(
    title="Sports ERP System API",
    description="FastAPI Backend for University Sports Resource Planning and AI Assistant",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for Streamlit frontend and cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router)
app.include_router(sports_router)
app.include_router(agent_router)

@app.get("/")
def root():
    return {
        "status": "online",
        "system": "Sports ERP System API",
        "version": "2.0.0",
        "documentation": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "database": "connected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
