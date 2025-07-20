import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, ParkingLot, ParkingSpot, Reservation
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg') 
#'Agg' backend for non-interactive plotting
import matplotlib.pyplot as plt
import io
import base64
from sqlalchemy import func 
# For database functions like min/max

app = Flask(__name__)
app.secret_key = 'koustav_strong_secret_key'  

# Configure DB
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'parking.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Helper function to convert UTC datetime to IST 
def utc_to_ist(utc_dt):
    if utc_dt is None:
        return None
    # IST is UTC + 5 hours 30 minutes
    return utc_dt + timedelta(hours=5, minutes=30)

# This is used to Create DB and Admin user if not exist
@app.before_request
def create_tables():
    # Here I Ensure that application context is available for SQLAlchemy
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='koustav').first()
        if not admin:
            admin_user = User(username='koustav', password=generate_password_hash('koustav99'), role='admin', full_name='Koustav Admin Das', address='Contai,WB', pin='721401')
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created!")

# ------------- ROUTES -------------------

@app.route('/')
def home():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.role == 'admin': # Add admin check
            return redirect(url_for('admin_dashboard'))
        elif user and user.role == 'user': # Add user check
            return redirect(url_for('user_dashboard'))
        else:
            session.pop('user_id', None)
            session.pop('role', None)
            flash('Your session is invalid, please log in again.', 'danger')
            return redirect(url_for('login'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role # Storing the role and user_id in session
            flash('Logged in successfully!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        password = request.form['password']
        address = request.form['address']
        pin = request.form['pin']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, password=hashed_password, role='user', full_name=full_name, address=address, pin=pin)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    view = request.args.get('view', 'parking_lots') # Default view

    parking_lots = []
    users = []
    all_past_reservations = []
    admin_chart_url = None
    earnings_chart_url = None

    if view == 'parking_lots':
        parking_lots = ParkingLot.query.all()
    elif view == 'users':
        users = User.query.filter_by(role='user').all()
    elif view == 'summary':
        all_past_reservations = Reservation.query.filter(Reservation.leaving_timestamp != None).all()
        for res in all_past_reservations:
            res.parking_timestamp_ist = utc_to_ist(res.parking_timestamp)
            res.leaving_timestamp_ist = utc_to_ist(res.leaving_timestamp)
        # Here I am calculating Parking Lot Occupancy Summary
        total_spots_per_lot = {lot.prime_location_name: lot.maximum_number_of_spots for lot in ParkingLot.query.all()}
        occupied_spots_per_lot = {}

        all_active_reservations = Reservation.query.filter(Reservation.leaving_timestamp == None).all()
        for res in all_active_reservations:
            # This will fetch spot and lot when accessed (Lazy loading)
            if res.spot and res.spot.lot:
                lot_name = res.spot.lot.prime_location_name
                occupied_spots_per_lot[lot_name] = occupied_spots_per_lot.get(lot_name, 0) + 1

        lot_names_occupancy = sorted(list(total_spots_per_lot.keys())) 
        occupied = [occupied_spots_per_lot.get(name, 0) for name in lot_names_occupancy]
        available = [total_spots_per_lot.get(name, 0) - occupied_spots_per_lot.get(name, 0) for name in lot_names_occupancy]

        if lot_names_occupancy:
            fig, ax = plt.subplots(figsize=(10, 6))
            bar_width = 0.35
            index = range(len(lot_names_occupancy))

            bar1 = ax.bar(index, occupied, bar_width, label='Occupied', color='red')
            bar2 = ax.bar([i + bar_width for i in index], available, bar_width, label='Available', color='green')

            ax.set_xlabel('Parking Lot')
            ax.set_ylabel('Number of Spots')
            ax.set_title('Parking Lot Occupancy Summary')
            ax.set_xticks([i + bar_width / 2 for i in index])
            ax.set_xticklabels(lot_names_occupancy, rotation=45, ha='right')
            ax.legend()
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            plt.tight_layout()

            for bars in [bar1, bar2]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0: 
                        ax.annotate(f'{int(height)}',
                                    xy=(bar.get_x() + bar.get_width() / 2, height),
                                    xytext=(0, 3),  
                                    textcoords="offset points",
                                    ha='center', va='bottom', fontsize=8)

            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            admin_chart_url = base64.b64encode(img.getvalue()).decode()
            plt.close(fig)

        # Generate Earnings Chart
        # This will fetch spot and lot when accessed
        earnings_data = db.session.query(
            ParkingLot.prime_location_name,
            func.sum(Reservation.total_cost)
        ).join(ParkingSpot, ParkingLot.id == ParkingSpot.lot_id).join(Reservation, ParkingSpot.id == Reservation.spot_id).filter(Reservation.total_cost.isnot(None)).group_by(ParkingLot.prime_location_name).all()

        lot_names_earnings = [row[0] for row in earnings_data]
        total_earnings = [row[1] for row in earnings_data]

        if lot_names_earnings:
            fig_earnings, ax_earnings = plt.subplots(figsize=(10, 6))
            bars_earnings = ax_earnings.bar(lot_names_earnings, total_earnings, color='skyblue')

            ax_earnings.set_xlabel('Parking Lot')
            ax_earnings.set_ylabel('Total Earnings (₹)')
            ax_earnings.set_title('Total Earnings from Parking Lots')
            ax_earnings.set_xticklabels(lot_names_earnings, rotation=45, ha='right')
            ax_earnings.grid(axis='y', linestyle='--', alpha=0.7)
            plt.tight_layout()

            for bar in bars_earnings:
                yval = bar.get_height()
                ax_earnings.annotate(f'₹{yval:.2f}',
                                    xy=(bar.get_x() + bar.get_width() / 2, yval),
                                    xytext=(0, 3), 
                                    textcoords="offset points",
                                    ha='center', va='bottom', fontsize=8)

            img_earnings = io.BytesIO()
            plt.savefig(img_earnings, format='png')
            img_earnings.seek(0)
            earnings_chart_url = base64.b64encode(img_earnings.getvalue()).decode()
            plt.close(fig_earnings)

    return render_template('admin_dashboard.html', parking_lots=parking_lots, users=users, view=view, all_past_reservations=all_past_reservations, admin_chart_url=admin_chart_url, earnings_chart_url=earnings_chart_url)

@app.route('/admin/create_parking_lot', methods=['GET', 'POST'])
def create_parking_lot():
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        prime_location_name = request.form['prime_location_name']
        price = float(request.form['price'])
        address = request.form['address']
        pin_code = request.form['pin_code']
        maximum_number_of_spots = int(request.form['maximum_number_of_spots'])

        existing_lot = ParkingLot.query.filter_by(prime_location_name=prime_location_name).first()
        if existing_lot:
            flash('A parking lot with this location name already exists.', 'danger')
        else:
            new_lot = ParkingLot(prime_location_name=prime_location_name, price=price, address=address, pin_code=pin_code, maximum_number_of_spots=maximum_number_of_spots)
            db.session.add(new_lot)
            db.session.commit()

            # Here I am Creating parking spots for the new lot
            for i in range(1, maximum_number_of_spots + 1):
                new_spot = ParkingSpot(lot_id=new_lot.id, spot_number=i, status='A')
                db.session.add(new_spot)
            db.session.commit()

            flash('Parking lot created successfully!', 'success')
            return redirect(url_for('admin_dashboard', view='parking_lots'))
    return render_template('create_parking_lot.html')

@app.route('/admin/edit_parking_lot/<int:lot_id>', methods=['GET', 'POST'])
def edit_parking_lot(lot_id):
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)

    if request.method == 'POST':
        lot.prime_location_name = request.form['prime_location_name']
        lot.price = float(request.form['price'])
        lot.address = request.form['address']
        lot.pin_code = request.form['pin_code']
        
        new_max_spots = int(request.form['maximum_number_of_spots'])
        
        # Here I am making sure that if the new max spots is less than currently occupied spots
        occupied_spots_count = ParkingSpot.query.filter_by(lot_id=lot.id, status='O').count() 
        if (occupied_spots_count == 0 and new_max_spots==0):
            flash('Please use the delete button to delete this Parking lot from the dashboard!', 'danger')
            return render_template('edit_parking_lot.html', lot=lot)   
        if new_max_spots < occupied_spots_count:
            flash(f'Cannot reduce max spots to {new_max_spots}. There are currently {occupied_spots_count} occupied spots.', 'danger')
            return render_template('edit_parking_lot.html', lot=lot)

        # Updating existing spots if max spots increased
        if new_max_spots > lot.maximum_number_of_spots:
            for i in range(lot.maximum_number_of_spots + 1, new_max_spots + 1):
                new_spot = ParkingSpot(lot_id=lot.id, spot_number=i, status='A')
                db.session.add(new_spot)
        # Removing spots if max spots decreased (only available ones)
        elif new_max_spots < lot.maximum_number_of_spots:
            occupied_spots = ParkingSpot.query.filter(
                ParkingSpot.lot_id == lot.id,
                ParkingSpot.status == 'O'  
            ).all()
            occupaied_spot_numbers = [spot.spot_number for spot in occupied_spots]
            max_occupaied_spot_number = max(occupaied_spot_numbers) if occupaied_spot_numbers else 0
            spots_to_delete = ParkingSpot.query.filter(
                ParkingSpot.lot_id == lot.id,
                ParkingSpot.spot_number > new_max_spots,
                ParkingSpot.status == 'A'
            ).all()
            if new_max_spots >= max_occupaied_spot_number:
                for spot in spots_to_delete:
                    db.session.delete(spot)
            else:
                flash(f'Cannot reduce max spots to {new_max_spots}. Since the spot number {max_occupaied_spot_number} is occupaied by a vehicle. So, you can reduce the value of max number of spot upto {max_occupaied_spot_number}', 'danger')
                return render_template('edit_parking_lot.html', lot=lot)

        lot.maximum_number_of_spots = new_max_spots
        
        db.session.commit()
        flash('Parking lot updated successfully!', 'success')
        return redirect(url_for('admin_dashboard', view='parking_lots'))
    
    return render_template('edit_parking_lot.html', lot=lot)

@app.route('/admin/delete_parking_lot/<int:lot_id>', methods=['POST'])
def delete_parking_lot(lot_id):
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Checking if there are any active reservations in this lot
    active_reservations_in_lot = Reservation.query.join(ParkingSpot).filter(
        ParkingSpot.lot_id == lot.id,
        Reservation.leaving_timestamp == None
    ).count()

    if active_reservations_in_lot > 0:
        flash(f'Cannot delete parking lot {lot.prime_location_name} as there are {active_reservations_in_lot} active reservations.', 'danger')
        return redirect(url_for('admin_dashboard', view='parking_lots'))

    ParkingSpot.query.filter_by(lot_id=lot.id).delete()
    
    db.session.delete(lot)
    db.session.commit()
    flash('Parking lot deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard', view='parking_lots'))

@app.route('/admin/parking_lot/<int:lot_id>/spots')
def view_spots(lot_id):
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    spots = ParkingSpot.query.filter_by(lot_id=lot_id).order_by(ParkingSpot.spot_number).all()

    spots_data = []
    for spot in spots:
        spot_info = {
            'spot_number': spot.spot_number,
            'status': spot.status,
            'reservation_id': None
        }
        
        if spot.status == 'O' and spot.active_reservation:
            spot_info['reservation_id'] = spot.active_reservation.id
        spots_data.append(spot_info)

    return render_template('view_spots.html', lot=lot, spots_data=spots_data)


@app.route('/admin/reservation_details/<int:reservation_id>')
def view_reservation_details(reservation_id):
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    reservation = Reservation.query.get_or_404(reservation_id)

    parking_lot_name = reservation.spot.lot.prime_location_name if reservation.spot and reservation.spot.lot else 'N/A'
    spot_number = reservation.spot.spot_number if reservation.spot else 'N/A' 
    user_full_name = reservation.user.full_name if reservation.user else 'N/A'
    parking_timestamp_ist = utc_to_ist(reservation.parking_timestamp)

    return render_template('reservation_details.html',
                           reservation=reservation,
                           id=reservation.spot.lot.id, 
                           parking_lot_name=parking_lot_name,
                           spot_number=spot_number,
                           user_full_name=user_full_name,
                           parking_timestamp_ist=parking_timestamp_ist,
                           vehicle_number=reservation.vehicle_number)

@app.route('/admin/release_spot/<int:spot_id>', methods=['POST'])
def release_spot(spot_id):
    if not is_admin():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    spot = ParkingSpot.query.get_or_404(spot_id)

    if spot.status == 'O' and spot.active_reservation:
        reservation = spot.active_reservation 
        reservation.leaving_timestamp = datetime.utcnow()
        # Here I Call the new calculate_total_cost method to calculate reservation cost
        reservation.total_cost = reservation.calculate_total_cost() 

        spot.status = 'A' # Mark spot as available
        db.session.commit()
        flash(f'Spot {spot.spot_number} in {spot.lot.prime_location_name} released. Total cost: ₹{reservation.total_cost:.2f}', 'success')
    else:
        flash('Spot is not currently occupied or no active reservation found.', 'info')

    return redirect(url_for('view_spots', lot_id=spot.lot_id))


# User Dashboard
@app.route('/user/dashboard')
def user_dashboard():
    if not is_user():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    parking_lots = ParkingLot.query.all() 
    
    active_reservations = Reservation.query.filter_by(user_id=user.id, leaving_timestamp=None).order_by(Reservation.parking_timestamp.desc()).all()
    past_reservations = Reservation.query.filter(Reservation.user_id == user.id, Reservation.leaving_timestamp.isnot(None)).order_by(Reservation.leaving_timestamp.desc()).all()

    # Convert timestamps to IST for display
    for res in active_reservations:
        res.parking_timestamp_ist = utc_to_ist(res.parking_timestamp)
    for res in past_reservations:
        res.parking_timestamp_ist = utc_to_ist(res.parking_timestamp)
        res.leaving_timestamp_ist = utc_to_ist(res.leaving_timestamp)

    total_parking_cost = sum(res.total_cost for res in past_reservations if res.total_cost is not None)

    return render_template('user_dashboard.html', user=user, parking_lots=parking_lots, current_reservations=active_reservations, past_reservations=past_reservations, total_parking_cost=total_parking_cost)

@app.route('/user/book_spot/<int:lot_id>', methods=['POST'])
def book_spot(lot_id):
    if not is_user():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    lot = ParkingLot.query.get_or_404(lot_id)

    available_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='A').order_by(ParkingSpot.spot_number).all()

    if not available_spots:
        flash('No spots available in this lot.', 'danger')
        return redirect(url_for('user_dashboard'))

    selected_spot = available_spots[0]

    return render_template('confirm_booking.html', user=user, lot=lot, spot_number=selected_spot.spot_number, spot_id=selected_spot.id)


@app.route('/user/confirm_booking', methods=['GET', 'POST'])
def confirm_booking():
    if not is_user():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session['user_id']
        spot_id = request.form['spot_id']
        vehicle_number = request.form['vehicle_number']
        
        user = User.query.get(user_id)
        spot = ParkingSpot.query.get(spot_id)

        if not user or not spot:
            flash('Error: User or spot not found.', 'danger')
            return redirect(url_for('user_dashboard'))
        
        if spot.status == 'O':
            flash('This spot has just been taken. Please select another.', 'danger')
            return redirect(url_for('book_spot', lot_id=spot.lot_id))

        # Update spot status
        spot.status = 'O'

        new_reservation = Reservation(
            spot_id=spot.id,
            user_id=user.id,
            parking_timestamp=datetime.utcnow(),
            parking_cost_per_unit=spot.lot.price, 
            vehicle_number=vehicle_number
        )
        db.session.add(new_reservation)
        db.session.commit()

        flash('Booking confirmed successfully!', 'success')
        return redirect(url_for('user_dashboard'))
    
    flash('Please select a spot to confirm booking.', 'info')
    return redirect(url_for('user_dashboard'))


@app.route('/user/release_my_spot/<int:reservation_id>', methods=['POST'])
def release_my_spot(reservation_id):
    if not is_user():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    reservation = Reservation.query.filter_by(id=reservation_id, user_id=user.id, leaving_timestamp=None).first()

    if reservation:
        reservation.leaving_timestamp = datetime.utcnow()
        # Calling the calculate_total_cost method to calculate total reservation cost
        reservation.total_cost = reservation.calculate_total_cost()
        
        # Again marking the spot as available
        spot = reservation.spot 
        spot.status = 'A'
        
        db.session.commit()
        flash(f'Your spot {spot.spot_number} in {spot.lot.prime_location_name} released. Total cost: ₹{reservation.total_cost:.2f}', 'success')
    else:
        flash('Reservation not found or already released.', 'danger')
    
    return redirect(url_for('user_dashboard'))


@app.route('/user/parking_history_chart')
def user_parking_history_chart():
    if not is_user():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    user_reservations = Reservation.query.filter(
        Reservation.user_id == user.id,
        Reservation.total_cost.isnot(None) # Only considering completed reservations
    ).order_by(Reservation.leaving_timestamp).all()

    # Group by parking lot and sum costs
    lot_costs = {}
    for res in user_reservations:
        if res.spot and res.spot.lot: # Lazy load spot and lot
            lot_name = res.spot.lot.prime_location_name
            lot_costs[lot_name] = lot_costs.get(lot_name, 0) + res.total_cost

    chart_url = None
    lot_names = []  
    costs = []      

    if lot_costs:
        lot_names = list(lot_costs.keys())
        costs = list(lot_costs.values())

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(lot_names, costs, color='purple')

        ax.set_xlabel('Parking Lot')
        ax.set_ylabel('Total Cost (₹)')
        ax.set_title(f'{user.username}\'s Parking Cost History per Lot')
        ax.set_xticklabels(lot_names, rotation=45, ha='right')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()

        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'₹{height:.2f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),  
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        chart_url = base64.b64encode(img.getvalue()).decode()
        plt.close(fig)

    return render_template('user_parking_history_chart.html', user=user, chart_url=chart_url)




# ------------- HELPER FUNCTIONS -----------------

def is_admin():
    if 'user_id' not in session:
        return False
    user = User.query.get(session['user_id'])
    return user and user.role == 'admin'

def is_user():
    if 'user_id' not in session:
        return False
    user = User.query.get(session['user_id'])
    return user and user.role == 'user'

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='koustav').first()
        if not admin:
            admin_user = User(username='koustav', password=generate_password_hash('koustav99'), role='admin', full_name='Koustav Admin Das', address='Contai,WB', pin='721401')
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created!")
    app.run(debug=True)
