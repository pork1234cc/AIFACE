"""订单 CRUD、分页和终态限制。"""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db import Base, create_db_engine
from app.schemas.orders import OrderCreate, OrderPatch
from app.services.orders import (
    BusinessError,
    create_order,
    get_order,
    list_orders,
    update_order,
    write_session,
)


def test_orders_crud_and_pagination(tmp_path):
    engine = create_db_engine(Settings(_env_file=None, AIFACE_DATABASE_PATH=tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    try:
        with write_session(engine) as session:
            first = create_order(session, OrderCreate(customer_name=" 小红 ", note="保留眼镜"))
            second = create_order(session, OrderCreate(customer_name="小蓝"))
            assert first.order_no != second.order_no
            first_id = first.id
        with write_session(engine) as session:
            result = list_orders(session, 1, 1, "draft", "小")
            assert result["total"] == 2 and len(result["items"]) == 1
            assert list_orders(session, 1, 20, None, "%")["total"] == 0
            update_order(session, first_id, OrderPatch(note="修改备注"))
        with write_session(engine) as session:
            order = get_order(session, first_id)
            assert order.customer_name == "小红" and order.note == "修改备注"
            order.status = "closed"
        with pytest.raises(BusinessError, match="只读"), write_session(engine) as session:
            update_order(session, first_id, OrderPatch(customer_name="不能修改"))
        with pytest.raises(BusinessError, match="不存在"), write_session(engine) as session:
            get_order(session, "missing")
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "payload", [{"customer_name": " "}, {"customer_name": None}, {"status": "ready"}]
)
def test_invalid_order_patch(payload):
    with pytest.raises(ValidationError):
        OrderPatch.model_validate(payload)
