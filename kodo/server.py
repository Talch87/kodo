"""
KODO REST API Server
Exposes Kodo orchestrator as HTTP endpoints for the UI to call.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import asyncio
import json
import os
from typing import Optional

from kodo.orchestrator import Kodo2Orchestrator

# Create FastAPI app
app = FastAPI(
    title="KODO API",
    description="Autonomous development orchestrator REST API",
    version="2.0.0"
)

# Allow CORS for the UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your UI domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ProcessRequest(BaseModel):
    """Request to process code through orchestrator"""
    code: str
    code_id: str
    test_code: Optional[str] = None
    specification: Optional[str] = None


class VerifyRequest(BaseModel):
    """Request to verify code"""
    code: str
    code_id: str
    test_code: Optional[str] = None


class ProcessResponse(BaseModel):
    """Response from orchestrator"""
    code_id: str
    verified: bool
    verification_score: float
    quality_passed: bool
    quality_score: float
    specification_compliance: float
    production_ready: bool
    production_score: float
    trust_level: str
    trust_score: float
    auto_action: str  # "deploy", "review", "reject"
    confidence: float
    reason: str
    errors_fixed: Optional[int] = None


class ReportResponse(BaseModel):
    """Full report for a code submission"""
    code_id: str
    report: dict


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "KODO API",
        "version": "2.0.0"
    }


@app.post("/api/process", response_model=ProcessResponse)
async def process_code(request: ProcessRequest):
    """
    Process code through the full KODO orchestrator pipeline.
    
    Returns decision (DEPLOY/REVIEW/REJECT) with confidence score.
    """
    try:
        orchestrator = Kodo2Orchestrator()
        
        result = await orchestrator.process_code(
            code=request.code,
            code_id=request.code_id,
            test_code=request.test_code,
            specification=request.specification,
        )
        
        return ProcessResponse(
            code_id=result.code_id,
            verified=result.verified,
            verification_score=result.verification_score,
            quality_passed=result.quality_passed,
            quality_score=result.quality_score,
            specification_compliance=result.specification_compliance,
            production_ready=result.production_ready,
            production_score=result.production_score,
            trust_level=result.trust_level,
            trust_score=result.trust_score,
            auto_action=result.auto_action,
            confidence=result.confidence,
            reason=result.reason,
            errors_fixed=result.errors_fixed if result.healed else None,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/verify", response_model=dict)
async def verify_code(request: VerifyRequest):
    """
    Verify code only (without full orchestration).
    """
    try:
        from kodo.verification import VerificationEngine
        
        engine = VerificationEngine()
        result = await engine.verify(
            code=request.code,
            code_id=request.code_id,
            test_code=request.test_code or "",
        )
        
        return {
            "code_id": request.code_id,
            "correctness_score": result.correctness_score,
            "status": result.status.value,
            "confidence_level": result.confidence_level,
            "decision": result.decision,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report/{code_id}", response_model=ReportResponse)
async def get_report(code_id: str):
    """
    Get the full report for a previously processed code submission.
    """
    try:
        orchestrator = Kodo2Orchestrator()
        report = orchestrator.get_full_report(code_id)
        
        return ReportResponse(
            code_id=code_id,
            report=report
        )
    
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Report not found: {str(e)}")


@app.get("/api/stats")
async def get_stats():
    """
    Get aggregate statistics across all processed code.
    """
    try:
        orchestrator = Kodo2Orchestrator()
        stats = orchestrator.get_stats()
        return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/feedback")
async def submit_feedback(data: dict):
    """
    Submit feedback on a decision for model improvement.
    """
    try:
        code_id = data.get("code_id")
        feedback = data.get("feedback")
        was_correct = data.get("was_correct")
        
        if not code_id or feedback is None:
            raise ValueError("code_id and feedback required")
        
        orchestrator = Kodo2Orchestrator()
        orchestrator.record_feedback(code_id, feedback, was_correct)
        
        return {
            "status": "received",
            "code_id": code_id,
            "message": "Feedback recorded for model improvement"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Run with: python -m kodo.server
    # Or: uvicorn kodo.server:app --reload --port 8000
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False
    )
