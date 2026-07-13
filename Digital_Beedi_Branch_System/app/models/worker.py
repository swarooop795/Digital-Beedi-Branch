from datetime import datetime
from app import db

class Worker:
    def __init__(self, name, worker_id, contact, address, aadhar_number):
        self.name = name
        self.worker_id = worker_id
        self.contact = contact
        self.address = address
        self.aadhar_number = aadhar_number
        self.join_date = datetime.now()

    def to_dict(self):
        return {
            'name': self.name,
            'worker_id': self.worker_id,
            'contact': self.contact,
            'address': self.address,
            'aadhar_number': self.aadhar_number,
            'join_date': self.join_date
        }

    @staticmethod
    def create(data):
        worker = Worker(
            name=data['name'],
            worker_id=data['worker_id'],
            contact=data['contact'],
            address=data['address'],
            aadhar_number=data['aadhar_number']
        )
        db.workers.insert_one(worker.to_dict())
        return worker

    @staticmethod
    def get_all():
        return list(db.workers.find())