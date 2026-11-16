"""
DBA tickets and instances.

    GET  /api/v1/tenants/{slug}/tickets                          TicketSummary[]
    GET  /api/v1/tenants/{slug}/tickets/{id}                     TicketDetail (with runbook)
    GET  /api/v1/tenants/{slug}/tickets/{id}/scripts/{name}      ScriptSource
    POST /api/v1/tenants/{slug}/tickets/{id}/scripts/{name}/run  RunResult
         body RunRequest {sandbox=true, maxRows, continueOnError}
         destructive scripts need header  X-Onboarded-Confirm: <id>/<name>
    GET  /api/v1/instances                                       InstanceSummary[]
    GET  /api/v1/instances/{slug}                                InstanceSummary
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header

from onboarded_api import schemas
from onboarded_api.deps import get_settings
from onboarded_api.services.dba_service import DbaService, InstanceService
from onboarded_api.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["dba"])


def get_dba(settings: Annotated[Settings, Depends(get_settings)]) -> DbaService:
    return DbaService(settings)


def get_instances(settings: Annotated[Settings, Depends(get_settings)]) -> InstanceService:
    return InstanceService(settings)


Dba = Annotated[DbaService, Depends(get_dba)]
Instances = Annotated[InstanceService, Depends(get_instances)]


@router.get("/tenants/{slug}/tickets", response_model=list[schemas.TicketSummary])
def list_tickets(slug: str, dba: Dba):
    return dba.tickets(slug)


@router.get("/tenants/{slug}/tickets/{ticket_id}", response_model=schemas.TicketDetail)
def get_ticket(slug: str, ticket_id: str, dba: Dba):
    return dba.ticket(slug, ticket_id)


@router.get("/tenants/{slug}/tickets/{ticket_id}/scripts/{name}", response_model=schemas.ScriptSource)
def get_script(slug: str, ticket_id: str, name: str, dba: Dba):
    return dba.script_source(slug, ticket_id, name)


@router.post("/tenants/{slug}/tickets/{ticket_id}/scripts/{name}/run", response_model=schemas.RunResult)
def run_script(slug: str, ticket_id: str, name: str, body: schemas.RunRequest, dba: Dba,
               x_onboarded_confirm: Annotated[Optional[str], Header()] = None):
    return dba.run(slug, ticket_id, name, sandbox=body.sandbox, confirm=x_onboarded_confirm,
                   max_rows=body.maxRows, continue_on_error=body.continueOnError)


@router.get("/instances", response_model=list[schemas.InstanceSummary])
def list_instances(inst: Instances):
    return inst.list()


@router.get("/instances/{slug}", response_model=schemas.InstanceSummary)
def get_instance(slug: str, inst: Instances):
    return inst.get(slug)
