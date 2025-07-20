from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(10), nullable=False) 
    full_name = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    pin = db.Column(db.String(10), nullable=True)
    
    reservations = db.relationship('Reservation', backref='user', lazy=True)

class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prime_location_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False) 
    address = db.Column(db.String(200), nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    maximum_number_of_spots = db.Column(db.Integer, nullable=False)
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True, cascade="all, delete-orphan")

class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Internal database ID
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    spot_number = db.Column(db.Integer, nullable=False) 
    status = db.Column(db.String(1), nullable=False, default='A')  

    # Ensure that spot_number is unique within each parking lot
    __table_args__ = (db.UniqueConstraint('lot_id', 'spot_number', name='_lot_spot_uc'),)
    # This relationship defines an active reservation for a spot.
    # Updated primaryjoin to explicitly join on spot_id and null leaving_timestamp
    reservations = db.relationship('Reservation', backref='spot', lazy=True) 
    active_reservation = db.relationship('Reservation', backref='active_spot_link', uselist=False,
                                  primaryjoin="and_(ParkingSpot.id == Reservation.spot_id, Reservation.leaving_timestamp == None)")

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parking_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    leaving_timestamp = db.Column(db.DateTime, nullable=True)
    parking_cost_per_unit = db.Column(db.Float, nullable=False) 
    total_cost = db.Column(db.Float, nullable=True)
    vehicle_number = db.Column(db.String(20), nullable=True)

    def calculate_total_cost(self):
        #Calculates the total parking cost for the reservation.
        #Cost is calculated per hour, rounded up to the nearest hour.
        if self.parking_timestamp and self.leaving_timestamp and self.parking_cost_per_unit is not None:
            duration = self.leaving_timestamp - self.parking_timestamp
            total_seconds = duration.total_seconds()
            # Calculate hours, rounding up to the nearest hour
            # If duration is 0 seconds, cost is for 1 hour.
            if total_seconds <= 0:
                hours_parked = 1.0
            else:
                hours_parked = (total_seconds / 3600.0) # Convert seconds to hours
                # Round up to the nearest whole hour
                if hours_parked % 1 != 0:
                    hours_parked = int(hours_parked) + 1
                else:
                    hours_parked = int(hours_parked)

            return round(hours_parked * self.parking_cost_per_unit, 2)
        return 0.0 # This done for incomplete data
