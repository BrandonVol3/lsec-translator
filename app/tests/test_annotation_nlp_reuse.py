"""Pruebas de reutilización del servicio NLP en anotaciones y MLOps."""

from __future__ import annotations

from app.api import annotation_endpoints
from app.services.nlp_service import LSECTranslatorService


def test_annotation_router_uses_injected_nlp_service():
    service = object.__new__(LSECTranslatorService)
    annotation_endpoints.set_annotation_nlp_service(service)
    try:
        assert annotation_endpoints._get_annotation_nlp_service() is service
    finally:
        annotation_endpoints.set_annotation_nlp_service(None)
