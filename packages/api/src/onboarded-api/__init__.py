"""
onboarded_api — the Onboarded REST API (FastAPI).

Layout:
    settings   Settings (every OB_API_* knob, read once from the environment)
    errors     ApiError hierarchy → RFC 9457 problem+json (mapped in main.py)
    schemas    Pydantic request/response models (wire names = camelCase)
    services/  framework-free logic — importable and testable without FastAPI
    routers/   thin FastAPI routers over services/
    main       create_app() factory: lifespan, error handlers, CORS, routers

Run as ``onboarded-api`` (installed), ``python -m onboarded_api`` or
``uvicorn onboarded_api.main:create_app --factory``. See packages/api/README.md.

Importing this package does not import FastAPI; only ``main``, ``deps`` and ``routers`` do.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
