"""内置风格只读，自定义风格保存于当前数据库，不隐式附加示例图。"""

import json
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models.orders import CustomStyle, StylePreviewTask, utc_now
from app.services.orders import BusinessError


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_style: str
    subject_rule: str
    render_rule: str
    negative_rule: str


class PreviewInfo(BaseModel):
    task_id: str
    request_key: str
    status: str
    error_message: str | None
    can_resume_download: bool


class Style(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style_id: str
    is_builtin: bool = True
    style_name: str
    version: str
    status: Literal["active"]
    cover_image: str | None
    cover_stale: bool = False
    preview: PreviewInfo | None = None
    reference_images: list[str]
    description: str
    initial_count: Literal[1]
    revision_count: Literal[1]
    allowed_controls: list[str]
    prompt_template: PromptTemplate
    qa_checklist: list[str]


class CustomStyleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    style_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
    ]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class CustomStyleUpdate(CustomStyleCreate):
    expected_version: int = Field(ge=1)


def custom_style_data(row: CustomStyle, task: StylePreviewTask | None = None) -> Style:
    return Style(
        style_id=row.id,
        is_builtin=False,
        style_name=row.name,
        version=str(row.version),
        status="active",
        cover_image=(
            f"/api/styles/{row.id}/previews/{row.cover_task_id}/content"
            if row.cover_task_id
            else None
        ),
        cover_stale=row.cover_task_id is not None and row.cover_version != row.version,
        preview=PreviewInfo(
            task_id=task.id,
            request_key=task.idempotency_key,
            status=task.status,
            error_message=task.error_message,
            can_resume_download=task.status == "failed" and task.download_url is not None,
        )
        if task
        else None,
        reference_images=[],
        description=row.description,
        initial_count=1,
        revision_count=1,
        allowed_controls=["changes", "extra_requirement", "aspect_ratio"],
        prompt_template=PromptTemplate(
            system_style=row.prompt,
            subject_rule="风格仅控制表现方式，画面内容来自底图及明确修改要求。",
            render_rule="未要求修改的人物、物品、动作与布局默认保留。",
            negative_rule="不增加未要求的内容。",
        ),
        qa_checklist=[],
    )


def load_style(style_id: str = "q_crayon_001", session: Session | None = None) -> Style:
    if style_id == "q_crayon_001":
        with (PROJECT_ROOT / "styles/q_crayon_001/style.json").open(encoding="utf-8") as source:
            return Style.model_validate(json.load(source))
    row = session.get(CustomStyle, style_id) if session is not None else None
    if row is None:
        raise BusinessError(404, "style_not_found", "风格不存在，请重新选择")
    task = session.get(StylePreviewTask, row.preview_task_id) if row.preview_task_id else None
    return custom_style_data(row, task)


def list_styles(session: Session) -> list[Style]:
    rows = session.execute(
        select(CustomStyle, StylePreviewTask)
        .outerjoin(
            StylePreviewTask,
            CustomStyle.preview_task_id == StylePreviewTask.id,
        )
        .order_by(CustomStyle.created_at, CustomStyle.id)
    )
    return [load_style(), *[custom_style_data(row, task) for row, task in rows]]


def create_style(session: Session, payload: CustomStyleCreate) -> Style:
    row = CustomStyle(
        id=f"custom_{uuid4().hex}",
        name=payload.style_name,
        description=payload.description,
        prompt=payload.prompt,
    )
    session.add(row)
    session.flush()
    return custom_style_data(row)


def update_style(session: Session, style_id: str, payload: CustomStyleUpdate) -> Style:
    if style_id == "q_crayon_001":
        raise BusinessError(403, "builtin_style_readonly", "内置风格只读，请新建自定义风格")
    row = session.get(CustomStyle, style_id)
    if row is None:
        raise BusinessError(404, "style_not_found", "风格不存在")
    if row.version != payload.expected_version:
        raise BusinessError(409, "style_version_conflict", "风格已被更新，请重新打开后编辑")
    row.name, row.description, row.prompt = payload.style_name, payload.description, payload.prompt
    row.version += 1
    row.updated_at = utc_now()
    session.flush()
    return load_style(row.id, session)
