from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import tensorflow as tf
from tensorflow.keras.preprocessing import image
import numpy as np
import os
from PIL import Image
import json
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta

app = Flask(__name__)
app.secret_key = 'jrpwerfgnhjnbvawsedfghjaer'

# --- Database connection function ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="nutrival"
    )

# --- Load trained model ---
model = tf.keras.models.load_model('saved_model/food_model.h5')

# --- Load class labels ---
with open('dataset/labels.txt', 'r') as f:
    class_names = [line.strip() for line in f.readlines()]

# --- Load calorie and nutrient data ---
calorie_file = os.path.join(os.path.dirname(__file__), 'data', 'calorie.json')
if os.path.exists(calorie_file):
    with open(calorie_file, 'r') as f:
        calorie_data = json.load(f)
    print(f"✓ Loaded calorie data for {len(calorie_data)} foods")
    print(f"✓ Sample foods: {list(calorie_data.keys())[:5]}")
else:
    calorie_data = {}
    print(f"✗ WARNING: calorie.json not found at {calorie_file}")
    print(f"✗ Creating empty calorie_data dict")

# --- Health tips dictionary ---
health_tips = {
    "biryani": "Try using brown rice and less oil for a healthier version.",
    "dosa": "Pair with chutney instead of oily sambar for fewer calories.",
    "samosa": "Air fry instead of deep frying to reduce fat.",
    "idli": "Light and healthy breakfast option, rich in carbs and easy to digest.",
    "pulao": "Add more veggies and less ghee for better nutrition.",
    "butter_chicken": "Use grilled chicken and low-fat yogurt for a lighter recipe.",
    "poha": "Add peanuts for protein but control oil quantity.",
    "besan_laddu": "Use jaggery instead of sugar and ghee in moderation.",
    "chole_bhature": "Limit portion size – high in calories but delicious!",
    "vada_pav": "Enjoy occasionally; opt for air-fried version to cut fat."
}

# --- Ensure upload folder exists ---
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Signup Route ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            flash('Email already registered. Please login.', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))

        cursor.execute(
            "INSERT INTO users (username, email, password, created_at) VALUES (%s, %s, %s, NOW())",
            (username, email, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

# --- Login Route ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        email = request.form['email']
        password = request.form['password']

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            flash('Login successful!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))  # ✅ FIXED: Changed from 'home' to 'index'
        else:
            flash('Invalid email or password.', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))

    return render_template('login.html')
# --- Logout Route ---
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# --- Home (Index) Route ---
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('home'))

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

# --- Prediction Route ---
@app.route('/predict', methods=['POST'])
def predict():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        return "No file part"

    file = request.files['file']
    if file.filename == '':
        return "No selected file"

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # Preprocess image
    img = Image.open(filepath).resize((128, 128))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0) / 255.0

    predictions = model.predict(img_array)
    score = tf.nn.softmax(predictions[0])
    predicted_label = class_names[np.argmax(score)]
    confidence = round(100 * np.max(score), 2)

    key = predicted_label.lower().replace(" ", "_")
    nutrients = calorie_data.get(key, {"calories": 250, "protein": 8, "carbs": 35, "fat": 10})  # Default values
    
    # If not found, log it
    if key not in calorie_data:
        print(f"WARNING: '{key}' not found in calorie_data. Using default values.")
        print(f"Available keys: {list(calorie_data.keys())[:10]}...")  # Show first 10 keys

    tip = health_tips.get(key, "Eat in moderation and stay active!")

    current_date = datetime.utcnow().date().isoformat()
    current_time = datetime.utcnow().time().strftime('%H:%M:%S')

    print(f"Prediction: {predicted_label}, Key: {key}, Calories: {nutrients['calories']}")  # Debug

    return render_template(
        'index.html',
        prediction=predicted_label,
        confidence=confidence,
        calories=nutrients['calories'],
        protein=nutrients['protein'],
        carbs=nutrients['carbs'],
        fat=nutrients['fat'],
        tip=tip,
        img_path=filepath,
        username=session['username'],
        current_date=current_date,
        current_time=current_time
    )

# --- Add Food Entry Route ---
@app.route('/add_food', methods=['POST'])
def add_food():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    data = request.get_json(force=False)

    if data is not None:
        dish = data.get('dish')
        calories = float(data.get('calories', 0))
        protein = float(data.get('protein', 0))
        carbs = float(data.get('carbs', 0))
        fat = float(data.get('fat', 0))
        user_id = session['user_id']
        username = session['username']

        print(f"Adding food: {dish}, Calories: {calories}")  # Debug

        # Insert into food_tracker
        cursor.execute("""
            INSERT INTO food_tracker (user_id, food_name, calories, protein, carbs, fat, date, time)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE(), CURTIME())
        """, (user_id, dish, calories, protein, carbs, fat))
        conn.commit()

        # Update leaderboard
        update_leaderboard(user_id, username, calories, conn)

        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM food_tracker WHERE entry_id=%s", (new_id,))
        new_meal = cursor.fetchone()

        for key in new_meal:
            if isinstance(new_meal[key], (datetime, date, time, timedelta)):
                new_meal[key] = str(new_meal[key])

        cursor.close()
        conn.close()
        
        print(f"Successfully added: {new_meal}")  # Debug
        return jsonify(new_meal), 200

    # Form submission fallback
    food_name = request.form.get('food_name')
    calories = float(request.form.get('calories', 0))
    protein = float(request.form.get('protein', 0))
    carbs = float(request.form.get('carbs', 0))
    fat = float(request.form.get('fat', 0))
    user_id = session['user_id']
    username = session['username']

    cursor.execute("""
        INSERT INTO food_tracker (user_id, food_name, calories, protein, carbs, fat, date, time)
        VALUES (%s, %s, %s, %s, %s, %s, CURDATE(), CURTIME())
    """, (user_id, food_name, calories, protein, carbs, fat))
    conn.commit()

    # Update leaderboard
    update_leaderboard(user_id, username, calories, conn)

    cursor.close()
    conn.close()

    return redirect(url_for('tracker'))

# --- Helper function to update leaderboard ---
def update_leaderboard(user_id, username, calories, conn):
    """Update or insert user in leaderboard table"""
    cursor = conn.cursor()
    
    # Check if user exists in leaderboard
    cursor.execute("SELECT total_calories FROM leaderboard WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    
    if result:
        # Update existing record
        new_total = result[0] + int(calories)
        cursor.execute("""
            UPDATE leaderboard 
            SET total_calories = %s
            WHERE user_id = %s
        """, (new_total, user_id))
        print(f"Updated leaderboard: {username} -> {new_total} calories")
    else:
        # Insert new record
        cursor.execute("""
            INSERT INTO leaderboard (user_id, username, total_calories, streak)
            VALUES (%s, %s, %s, 0)
        """, (user_id, username, int(calories)))
        print(f"Inserted into leaderboard: {username} -> {calories} calories")
    
    conn.commit()
    cursor.close()

# --- Tracker Route ---
@app.route('/tracker')
def tracker():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    today = datetime.now().strftime('%Y-%m-%d')

    # Today's meals
    cursor.execute("""
        SELECT food_name, calories, protein, carbs, fat, date, time
        FROM food_tracker
        WHERE user_id=%s AND date=%s
    """, (user_id, today))
    meals = cursor.fetchall()

    for meal in meals:
        for key in meal:
            if isinstance(meal[key], (datetime, date, time, timedelta)):
                meal[key] = str(meal[key])

    # Today's totals
    cursor.execute("""
        SELECT 
            COALESCE(SUM(calories), 0) AS total_calories,
            COALESCE(SUM(protein), 0) AS total_protein,
            COALESCE(SUM(carbs), 0) AS total_carbs,
            COALESCE(SUM(fat), 0) AS total_fat
        FROM food_tracker
        WHERE user_id=%s AND date=%s
    """, (user_id, today))
    today_totals = cursor.fetchone()

    # Week total (last 7 days)
    cursor.execute("""
        SELECT COALESCE(SUM(calories), 0) AS week_calories
        FROM food_tracker
        WHERE user_id=%s
        AND date >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
        AND date <= CURDATE()
    """, (user_id,))
    week_totals = cursor.fetchone()

    # Month total
    cursor.execute("""
        SELECT COALESCE(SUM(calories), 0) AS month_calories
        FROM food_tracker
        WHERE user_id=%s
        AND MONTH(date) = MONTH(CURDATE())
        AND YEAR(date) = YEAR(CURDATE())
    """, (user_id,))
    month_totals = cursor.fetchone()

    # Daily average
    cursor.execute("""
        SELECT COALESCE(AVG(daily_cal), 0) AS avg_calories
        FROM (
            SELECT date, SUM(calories) AS daily_cal
            FROM food_tracker
            WHERE user_id=%s
            GROUP BY date
        ) AS t
    """, (user_id,))
    avg_totals = cursor.fetchone()

    # Weekly chart data
    cursor.execute("""
        SELECT date, SUM(calories) AS total_cal
        FROM food_tracker
        WHERE user_id=%s
        GROUP BY date
        ORDER BY date ASC
    """, (user_id,))
    weekly_rows = cursor.fetchall()

    weekly_data = {str(row['date']): row['total_cal'] for row in weekly_rows}

    cursor.close()
    conn.close()

    return render_template(
        'tracker.html',
        meals=meals,
        weekly_data=weekly_data,
        total_calories=int(today_totals['total_calories']),
        total_protein=float(today_totals['total_protein']),
        total_carbs=float(today_totals['total_carbs']),
        total_fat=float(today_totals['total_fat']),
        week_calories=int(week_totals['week_calories']),
        month_calories=int(month_totals['month_calories']),
        avg_calories=int(avg_totals['avg_calories']),
        goal=2000,
        user=session
    )

@app.route('/get_food_data')
def get_food_data():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT `date`, SUM(calories) AS total_calories
        FROM food_tracker
        WHERE user_id = %s
        GROUP BY `date`
        ORDER BY `date` ASC
    """, (user_id,))
    
    result = cursor.fetchall()
    
    for row in result:
        if isinstance(row['date'], date):
            row['date'] = str(row['date'])
    
    cursor.close()
    conn.close()

    return jsonify(result)

# --- Leaderboard Route ---
@app.route('/leaderboard')
def leaderboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    username = session.get('username', 'Guest')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch top 10 users from leaderboard table
    query = """
        SELECT username, total_calories
        FROM leaderboard
        WHERE total_calories > 0
        ORDER BY total_calories DESC
        LIMIT 10
    """
    cursor.execute(query)
    results = cursor.fetchall()

    top_users = [(row[0], int(row[1]) if row[1] else 0) for row in results]
    
    print(f"Leaderboard data: {top_users}")  # Debug log

    cursor.close()
    conn.close()

    return render_template('leaderboard.html', top_users=top_users, username=username)

# --- Sync Leaderboard Route (one-time sync for existing data) ---
@app.route('/sync_leaderboard')
def sync_leaderboard():
    """One-time sync to populate leaderboard from existing food_tracker data"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all users with their total calories from food_tracker
    cursor.execute("""
        SELECT u.user_id, u.username, COALESCE(SUM(f.calories), 0) AS total_calories
        FROM users u
        LEFT JOIN food_tracker f ON f.user_id = u.user_id
        GROUP BY u.user_id, u.username
    """)
    users_data = cursor.fetchall()
    
    # Clear existing leaderboard
    cursor.execute("DELETE FROM leaderboard")
    
    # Insert fresh data
    for user_id, username, total_calories in users_data:
        if total_calories > 0:
            cursor.execute("""
                INSERT INTO leaderboard (user_id, username, total_calories, streak)
                VALUES (%s, %s, %s, 0)
            """, (user_id, username, int(total_calories)))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Leaderboard synced successfully!', 'success')
    return redirect(url_for('leaderboard'))

if __name__ == '__main__':
    app.run(debug=True, port=8000)
