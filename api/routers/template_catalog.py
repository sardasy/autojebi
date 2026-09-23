"""v2 template catalog with content-bound origin labels, preserving legacy catalog fields."""
from pydantic import BaseModel

from api.models.notices import HwpTemplateRecord
from api.routers.documents import list_hwp_templates
from api.workspace.template_provenance import TemplateProvenance, inspect_provenance


class WorkspaceTemplateRecord(HwpTemplateRecord):
    provenance: TemplateProvenance


class WorkspaceTemplateList(BaseModel):
    items: list[WorkspaceTemplateRecord]


def list_workspace_templates() -> WorkspaceTemplateList:
    return WorkspaceTemplateList(items=[WorkspaceTemplateRecord(
        **template.model_dump(), provenance=inspect_provenance(template.model_dump()))
        for template in list_hwp_templates().items])
