"""订单持久化和事务入口；SQLite 写操作先获取写锁再读取约束。"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Engine, func, or_, select, text
from sqlalchemy.orm import Session

from app.models.orders import Asset, Order, new_id, utc_now
from app.schemas.orders import OrderCreate, OrderPatch


class BusinessError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


@contextmanager
def write_session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        try:
            session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_order(session: Session, order_id: str, *, editable: bool = False) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise BusinessError(404, "order_not_found", "订单不存在")
    if editable and order.status in {"completed", "closed"}:
        raise BusinessError(409, "order_readonly", "已完成或关闭的订单只读")
    return order


def get_assets(session: Session, order_id: str) -> list[Asset]:
    return list(
        session.scalars(
            select(Asset).where(Asset.order_id == order_id).order_by(Asset.sort_index, Asset.id)
        )
    )


def asset_data(asset: Asset) -> dict:
    return {
        key: getattr(asset, key)
        for key in (
            "id",
            "order_id",
            "kind",
            "input_role",
            "is_active_input",
            "original_name",
            "mime_type",
            "byte_size",
            "width",
            "height",
            "review_status",
            "sort_index",
            "created_at",
        )
    } | {"content_url": f"/api/images/{asset.id}/content"}


def order_data(order: Order) -> dict:
    return {
        key: getattr(order, key)
        for key in (
            "id",
            "order_no",
            "customer_name",
            "note",
            "source_channel",
            "style_id",
            "status",
            "created_at",
            "updated_at",
        )
    } | {"params": order.params_json}


def create_order(session: Session, payload: OrderCreate) -> Order:
    order_id = new_id()
    order = Order(
        id=order_id,
        order_no=f"AF-{datetime.now(UTC):%Y%m%d}-{order_id.replace('-', '').upper()}",
        **payload.model_dump(),
    )
    session.add(order)
    session.flush()
    return order


def update_order(session: Session, order_id: str, payload: OrderPatch) -> Order:
    order = get_order(session, order_id, editable=True)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    order.updated_at = utc_now()
    return order


def list_orders(session: Session, page: int, page_size: int, status: str | None, q: str) -> dict:
    query = select(Order)
    if status:
        query = query.where(Order.status == status)
    if q.strip():
        query = query.where(
            or_(
                Order.customer_name.contains(q.strip(), autoescape=True),
                Order.order_no.contains(q.strip(), autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    orders = session.scalars(
        query.order_by(Order.created_at.desc(), Order.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [order_data(order) for order in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
