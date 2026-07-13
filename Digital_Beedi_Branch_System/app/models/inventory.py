from datetime import datetime


class Inventory:
    def __init__(self, item_name, quantity, type_of_item):
        self.item_name = item_name
        self.quantity = quantity
        self.type_of_item = type_of_item  # raw_material or finished_goods
        self.last_updated = datetime.now()

    def to_dict(self):
        return {
            'item_name': self.item_name,
            'quantity': self.quantity,
            'type_of_item': self.type_of_item,
            'last_updated': self.last_updated
        }


    @staticmethod
    def add_item(data):
        from app.models.database import get_db
        db = get_db()
        inventory = Inventory(
            item_name=data['item_name'],
            quantity=data['quantity'],
            type_of_item=data['type_of_item']
        )
        db.execute(
            'INSERT INTO inventory (item_name, quantity, type_of_item, last_updated) VALUES (?, ?, ?, ?)',
            (inventory.item_name, inventory.quantity, inventory.type_of_item, inventory.last_updated)
        )
        db.commit()
        return inventory


    @staticmethod
    def update_quantity(item_name, quantity_change):
        from app.models.database import get_db
        db = get_db()
        item = db.execute('SELECT quantity FROM inventory WHERE item_name = ?', (item_name,)).fetchone()
        if item:
            new_quantity = item['quantity'] + quantity_change
            db.execute(
                'UPDATE inventory SET quantity = ?, last_updated = ? WHERE item_name = ?',
                (new_quantity, datetime.now(), item_name)
            )
            db.commit()
            return True
        return False