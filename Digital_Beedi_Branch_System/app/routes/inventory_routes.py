from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session
from app.models.inventory import Inventory

bp = Blueprint('inventory', __name__, url_prefix='/api/inventory')


# ---------------------------------------------------------
# ADMIN INVENTORY PAGE
# URL: /api/inventory/admin
# ---------------------------------------------------------
@bp.route('/admin', methods=['GET'])
def inventory_admin():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    items = Inventory.get_all()

    total_items = len(items)
    total_quantity = sum(float(item['quantity']) for item in items)

    raw_materials = [
        item for item in items
        if item['type_of_item'] == 'raw_material'
    ]

    finished_goods = [
        item for item in items
        if item['type_of_item'] == 'finished_goods'
    ]

    return render_template(
        'inventory_admin.html',
        items=items,
        total_items=total_items,
        total_quantity=total_quantity,
        raw_materials_count=len(raw_materials),
        finished_goods_count=len(finished_goods)
    )


# ---------------------------------------------------------
# ADD INVENTORY ITEM
# ---------------------------------------------------------
@bp.route('/', methods=['POST'])
def add_inventory():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json(silent=True)

    if not data:
        return jsonify({'error': 'Invalid request data'}), 400

    try:
        inventory = Inventory.add_item(data)

        return jsonify({
            'message': 'Inventory added successfully',
            'inventory': inventory.to_dict()
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ---------------------------------------------------------
# UPDATE STOCK QUANTITY
# ---------------------------------------------------------
@bp.route('/update', methods=['PUT'])
def update_inventory():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json(silent=True)

    if not data:
        return jsonify({'error': 'Invalid request data'}), 400

    try:
        item_name = data.get('item_name')
        quantity_change = float(data.get('quantity_change', 0))

        if not item_name:
            return jsonify({'error': 'Item name is required'}), 400

        success = Inventory.update_quantity(
            item_name,
            quantity_change
        )

        if success:
            return jsonify({
                'message': 'Inventory updated successfully'
            }), 200

        return jsonify({
            'error': 'Item not found'
        }), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ---------------------------------------------------------
# DELETE INVENTORY ITEM
# ---------------------------------------------------------
@bp.route('/delete/<int:item_id>', methods=['POST'])
def delete_inventory(item_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    try:
        if Inventory.delete_item(item_id):
            flash('Inventory item deleted successfully.', 'success')
        else:
            flash('Inventory item not found.', 'error')

    except Exception as e:
        flash(f'Error deleting inventory item: {str(e)}', 'error')

    return redirect(url_for('inventory.inventory_admin'))


# ---------------------------------------------------------
# EDIT INVENTORY ITEM
# ---------------------------------------------------------
@bp.route('/edit/<int:item_id>', methods=['POST'])
def edit_inventory(item_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    try:
        item_name = request.form.get('item_name', '').strip()
        quantity = float(request.form.get('quantity', 0))
        type_of_item = request.form.get('type_of_item', '').strip()

        if not item_name:
            flash('Item name is required.', 'error')
            return redirect(url_for('inventory.inventory_admin'))

        if quantity < 0:
            flash('Quantity cannot be negative.', 'error')
            return redirect(url_for('inventory.inventory_admin'))

        if type_of_item not in ('raw_material', 'finished_goods'):
            flash('Invalid inventory type.', 'error')
            return redirect(url_for('inventory.inventory_admin'))

        Inventory.edit_item(
            item_id,
            item_name,
            quantity,
            type_of_item
        )

        flash('Inventory item updated successfully.', 'success')

    except Exception as e:
        flash(f'Error updating inventory: {str(e)}', 'error')

    return redirect(url_for('inventory.inventory_admin'))
