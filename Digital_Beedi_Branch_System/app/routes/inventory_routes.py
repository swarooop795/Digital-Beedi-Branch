from flask import Blueprint, request, jsonify
from app.models.inventory import Inventory

bp = Blueprint('inventory', __name__, url_prefix='/api/inventory')

@bp.route('/', methods=['POST'])
def add_inventory():
    data = request.get_json()
    try:
        inventory = Inventory.add_item(data)
        return jsonify({'message': 'Inventory added successfully', 'inventory': inventory.to_dict()}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/update', methods=['PUT'])
def update_inventory():
    data = request.get_json()
    try:
        success = Inventory.update_quantity(data['item_name'], data['quantity_change'])
        if success:
            return jsonify({'message': 'Inventory updated successfully'}), 200
        return jsonify({'error': 'Item not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400