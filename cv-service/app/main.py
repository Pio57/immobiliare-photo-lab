from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dataset import router as dataset_router
from app.api.dataset import processed_router, runs_router
from app.api.experiment import router as experiment_router
from app.api.routes import router

app = FastAPI(
    title="immobiliare-photo-lab cv-service",
    description="Deterministic enhancement pipeline and fidelity gate.",
    version="0.1.0",
)
# Prototype: the service is reached through an ngrok tunnel by n8n Cloud and,
# optionally, by the Vite dev server. Tighten before any real deployment.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(dataset_router)
app.include_router(runs_router)
app.include_router(processed_router)
app.include_router(experiment_router)
