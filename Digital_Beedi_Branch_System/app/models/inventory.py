from datetime import datetime


class Inventory:

    def __init__(self, item_name, quantity, type_of_item):
        self.item_name = item_name
        self.quantity = float(quantity)
        self.type_of_item = type_of_item
        self.last_updated = datetime.now()

    def to_dict(self):
        return {
            'item_name': self.item_name,
            'quantity': self.quantity,
            'type_of_item': self.type_of_item,
            'last_updated': self.last_updated.isoformat()
        }

    # ---------------------------------------------------------
    # GET ALL INVENTORY
    # ---------------------------------------------------------
    @staticmethod
    def get_all():
        from app.models.database import get_db

        db = get_db()

        rows = db.execute("""
            SELECT
                id,
                item_name,
                quantity,
                type_of_item,
                last_updated
            FROM inventory
            ORDER BY item_name ASC
        """).fetchall()

        return rows

    # ---------------------------------------------------------
    # ADD ITEM
    # ---------------------------------------------------------
    @staticmethod
    def add_item(data):
        from app.models.database import get_db

        item_name = str(data.get('item_name', '')).strip()
        quantity = float(data.get('quantity', 0))
        type_of_item = str(
            data.get('type_of_item', '')
        ).strip()

        if not item_name:
            raise ValueError('Item name is required.')

        if quantity < 0:
            raise ValueError('Quantity cannot be negative.')

        if type_of_item not in (
            'raw_material',
            'finished_goods'
        ):
            raise ValueError('Invalid inventory type.')

        db = get_db()

        now = datetime.now().isoformat(
            sep=' ',
            timespec='seconds'
        )

        db.execute("""
            INSERT INTO inventory
            (
                item_name,
                quantity,
                type_of_item,
                last_updated
            )
            VALUES (?, ?, ?, ?)
        """, (
            item_name,
            quantity,
            type_of_item,
            now
        ))

        db.commit()

        return Inventory(
            item_name,
            quantity,
            type_of_item
        )

    # ---------------------------------------------------------
    # UPDATE QUANTITY
    # ---------------------------------------------------------
    @staticmethod
    def update_quantity(item_name, quantity_change):
        from app.models.database import get_db

        db = get_db()

        item = db.execute("""
            SELECT quantity
            FROM inventory
            WHERE item_name = ?
        """, (item_name,)).fetchone()

        if not item:
            return False

        new_quantity = float(item['quantity']) + float(
            quantity_change
        )

        if new_quantity < 0:
            raise ValueError(
                'Inventory quantity cannot be negative.'
            )

        now = datetime.now().isoformat(
            sep=' ',
            timespec='seconds'
        )

        db.execute("""
            UPDATE inventory
            SET
                quantity = ?,
                last_updated = ?
            WHERE item_name = ?
        """, (
            new_quantity,
            now,
            item_name
        ))

        db.commit()

        return True

    # ---------------------------------------------------------
    # EDIT ITEM
    # ---------------------------------------------------------
    @staticmethod
    def edit_item(
        item_id,
        item_name,
        quantity,
        type_of_item
    ):
        from app.models.database import get_db

        db = get_db()

        now = datetime.now().isoformat(
            sep=' ',
            timespec='seconds'
        )

        cursor = db.execute("""
            UPDATE inventory
            SET
                item_name = ?,
                quantity = ?,
                type_of_item = ?,
                last_updated = ?
            WHERE id = ?
        """, (
            item_name,
            quantity,
            type_of_item,
            now,
            item_id
        ))

        db.commit()

        if cursor.rowcount == 0:
            raise ValueError(
                'Inventory item not found.'
            )

        return True

    # ---------------------------------------------------------
    # DELETE ITEM
    # ---------------------------------------------------------
    @staticmethod
    def delete_item(item_id):
        from app.models.database import get_db

        db = get_db()

        cursor = db.execute("""
            DELETE FROM inventory
            WHERE id = ?
        """, (item_id,))

        db.commit()

        return cursor.rowcount > 0
