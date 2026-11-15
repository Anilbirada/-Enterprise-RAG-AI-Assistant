from fastapi import APIRouter
from app.api.v1.endpoints import auth, chat, documents, health, search

api_v1_router = APIRouter()

# Register sub-routers
api_v1_router.include_router(health.router, tags=["Health & Monitoring"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Session"])
api_v1_router.include_router(documents.router, tags=["Documents"])
api_v1_router.include_router(search.router, prefix="/search", tags=["Semantic & Hybrid Search"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["RAG Chat & Conversations"])
