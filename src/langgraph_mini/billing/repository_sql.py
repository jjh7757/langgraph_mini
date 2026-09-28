"""BillRepository의 Postgres 구현체. find_by_id는 SELECT ... FOR UPDATE로 잠근다 —
pay_bill()류가 상태를 읽고 바꾼 뒤 저장하는 동안 동시 요청을 막기 위함."""

from ..db.postgres import current_connection
from .domain import Bill, BillNotFoundError, BillStatus


class SqlBillRepository:
    def find_by_id(self, bill_id: str) -> Bill:
        conn = current_connection()
        row = conn.execute(
            "SELECT bill_id, owner_id, name, amount, due_date, status FROM bills "
            "WHERE bill_id = %s FOR UPDATE",
            (bill_id,),
        ).fetchone()
        if row is None:
            raise BillNotFoundError(bill_id)
        return _to_bill(row)

    def find_by_owner_id(self, owner_id: str) -> list[Bill]:
        conn = current_connection()
        rows = conn.execute(
            "SELECT bill_id, owner_id, name, amount, due_date, status FROM bills "
            "WHERE owner_id = %s",
            (owner_id,),
        ).fetchall()
        return [_to_bill(row) for row in rows]

    def save(self, bill: Bill) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO bills (bill_id, owner_id, name, amount, due_date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (bill_id) DO UPDATE
                SET owner_id = EXCLUDED.owner_id,
                    name = EXCLUDED.name,
                    amount = EXCLUDED.amount,
                    due_date = EXCLUDED.due_date,
                    status = EXCLUDED.status
            """,
            (bill.bill_id, bill.owner_id, bill.name, bill.amount, bill.due_date, bill.status.value),
        )


def _to_bill(row) -> Bill:
    bill_id, owner_id, name, amount, due_date, status = row
    return Bill(
        bill_id=bill_id,
        owner_id=owner_id,
        name=name,
        amount=amount,
        due_date=due_date,
        status=BillStatus(status),
    )
