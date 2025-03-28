# backend/app.py (v6: Added Cookie/Session Debugging in /profile)

import os
import json
import math
from flask import Flask, request, jsonify, session # Import session
from ultralytics import YOLO
import werkzeug.utils
from PIL import Image
from flask_cors import CORS
import secrets # For generating a secret key

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
MODEL_PATH = 'models/food_mvp_best_model.pt' # Ensure this path is correct
USER_DATA_FILE = 'users.json'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
CONFIDENCE_THRESHOLD = 0.25

# --- Initialize Flask App & CORS ---
app = Flask(__name__)
# IMPORTANT: Set a secret key for session management!
# app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16)) # <-- Comment this out
app.secret_key = 'your-fixed-secret-key-here-12345' # <-- ADD THIS LINE (Use any string)
print(f"Using Flask secret key (DEMO ONLY - HARDCODED): {app.secret_key[:5]}...") # Optional: update print

CORS(app, supports_credentials=True) # Enable CORS and allow credentials (cookies)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Helper Functions (User Data, TDEE Calc) ---
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f: return json.load(f)
        except json.JSONDecodeError: print("Warning: users.json is corrupted."); return {}
    else: return {}

def save_user_data(data):
    try:
        with open(USER_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
    except IOError as e: print(f"ERROR saving user data: {e}")

def calculate_tdee(profile):
    if not profile or not all(key in profile for key in ['weight', 'height', 'age', 'gender', 'activity_level']):
         print(f"Error calculating TDEE: Profile data incomplete. Profile: {profile}")
         return None
    try:
        weight_kg = float(profile['weight']); height_cm = float(profile['height'])
        age = int(profile['age']); gender = profile['gender'].lower()
        activity_level = profile['activity_level'].lower()
        if gender == 'male': bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
        elif gender == 'female': bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
        else: bmr = ((10*weight_kg)+(6.25*height_cm)-(5*age)+5 + (10*weight_kg)+(6.25*height_cm)-(5*age)-161) / 2
        activity_multipliers = {'sedentary': 1.2, 'lightly active': 1.375, 'moderately active': 1.55, 'very active': 1.725, 'extra active': 1.9}
        multiplier = activity_multipliers.get(activity_level, 1.375)
        tdee = bmr * multiplier
        return int(round(tdee))
    except (ValueError, TypeError) as e:
        print(f"Error calculating TDEE during conversion: {e}. Profile: {profile}")
        return None

# --- Model Loading ---
model = None
print(f"Attempting to load model from: {MODEL_PATH}")
if not os.path.exists(MODEL_PATH):
    print(f"FATAL ERROR: Model file not found: {MODEL_PATH}")
else:
    try: model = YOLO(MODEL_PATH); print("YOLO Model loaded successfully.")
    except Exception as e: print(f"FATAL ERROR: Error loading YOLO model: {e}"); model = None

# --- Food Names & Nutrition DB ---
food_names = [ # CRITICAL: Ensure this list matches your model's classes exactly!
    '-', 'beef carpaccio', 'beet salad', 'breakfast burrito', 'caesar salad', 'caprese salad', 'chicken quesadilla', 'chicken wings', 'clam chowder', 'club sandwich', 'deviled eggs', 'dumplings', 'eggplant', 'falafel', 'french fries', 'french toast', 'fried rice', 'gnocchi', 'greek salad', 'guacamole', 'gyoza', 'hamburger', 'hot dog', 'hummus', 'ice cream', 'lentil soup', 'macaroni and cheese', 'molokhia', 'mussels', 'nachos', 'omelette', 'onion rings', 'pancakes', 'samosa', 'sashimi', 'spring rolls', 'steak', 'stuffed grape leaves', 'sushi', 'sweet potato', 'tacos', 'waffles'
]
nutrition_db = { # CRITICAL: Ensure this is populated accurately!
    '-': {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0},
    # ... (Full populated nutrition_db goes here - truncated for brevity) ...
    'hamburger': {'calories': 350, 'protein': 20, 'carbs': 30, 'fat': 15},
    'french fries': {'calories': 365, 'protein': 4, 'carbs': 48, 'fat': 17},
    'chicken wings': {'calories': 90, 'protein': 9, 'carbs': 0, 'fat': 6},
    # ... Add all other entries ...
}

# --- Allowed File Helper ---
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- API Endpoints ---
@app.route('/')
def home(): return jsonify({"message": "Dietary Companion Backend API v3 is running!"}), 200

# --- Authentication ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(); username = data.get('username'); name = data.get('name')
    if not username or not name: return jsonify({"error": "Username and name required"}), 400
    user_db = load_user_data()
    if username in user_db: return jsonify({"error": "Username already exists"}), 409
    user_db[username] = {'name': name, 'profile': {}}; save_user_data(user_db)
    # Set session variables
    session['username'] = username; session['name'] = name; session['profile'] = {}
    session['calorie_goal'] = None
    session.modified = True # <-- Ensure session is marked to be saved
    print(f"User '{username}' registered, session set. Session Keys: {list(session.keys())}") # Log
    return jsonify({"message": "Registration successful", "user": {"username": username, "name": name, "profile": {}, "calorie_goal": None}}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(); username = data.get('username')
    if not username: return jsonify({"error": "Username required"}), 400
    user_db = load_user_data()
    if username not in user_db: return jsonify({"error": "Username not found"}), 404
    user_data = user_db[username]; profile = user_data.get('profile', {})
    calorie_goal = calculate_tdee(profile) # Calculate goal on login
    session['username'] = username; session['name'] = user_data.get('name', username)
    session['profile'] = profile; session['calorie_goal'] = calorie_goal
    session.modified = True # Mark modified on login too
    print(f"User '{username}' logged in. Profile keys: {list(profile.keys())}, Goal: {calorie_goal}")
    return jsonify({"message": "Login successful", "user": {"username": username, "name": session['name'], "profile": profile, "calorie_goal": calorie_goal}}), 200

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None); session.pop('name', None)
    session.pop('profile', None); session.pop('calorie_goal', None)
    session.modified = True
    print("User logged out."); return jsonify({"message": "Logout successful"}), 200

@app.route('/check_session', methods=['GET'])
def check_session():
    if 'username' in session:
        profile = session.get('profile', {}); goal = session.get('calorie_goal')
        if goal is None and profile and 'weight' in profile:
            print(f"[Check Session] Recalculating missing goal for '{session['username']}'")
            goal = calculate_tdee(profile); session['calorie_goal'] = goal; session.modified = True
        print(f"Check session: User '{session['username']}' IS logged in. Goal: {session.get('calorie_goal')}")
        return jsonify({"logged_in": True, "user": {"username": session['username'], "name": session.get('name'), "profile": profile, "calorie_goal": goal }}), 200
    else:
        print("Check session: No user logged in.")
        return jsonify({"logged_in": False}), 200

# --- Profile Management ---
@app.route('/profile', methods=['GET', 'POST'])
def profile_route():
    # --- ADDED DEBUGGING AT START ---
    print("-" * 20)
    print(f"[ROUTE /profile - {request.method}] Incoming Request Cookies: {request.cookies}")
    print(f"[ROUTE /profile - {request.method}] Flask Session BEFORE Check: {dict(session)}")
    # --- END DEBUGGING ---

    if 'username' not in session:
        print(f"[ROUTE /profile - {request.method}] Error: 'username' key NOT found in session. Rejecting.")
        return jsonify({"error": "Not logged in"}), 401

    # If username IS in session, continue
    print(f"[ROUTE /profile - {request.method}] Success: 'username' key FOUND in session ('{session['username']}')")
    username = session['username']
    user_db = load_user_data()
    if username not in user_db:
        print(f"[GET/POST /profile] Error: User '{username}' in session but not DB. Clearing.")
        session.clear(); session.modified = True
        return jsonify({"error": "User data missing"}), 404

    # --- Handle GET Request ---
    if request.method == 'GET':
        profile_data = user_db[username].get('profile', {})
        calorie_goal = session.get('calorie_goal')
        if calorie_goal is None and profile_data and 'weight' in profile_data:
            print(f"[GET /profile] Recalculating missing goal for '{username}'")
            calorie_goal = calculate_tdee(profile_data); session['calorie_goal'] = calorie_goal; session.modified = True
        print(f"[GET /profile] Returning profile for '{username}'. Goal: {session.get('calorie_goal')}")
        return jsonify({"profile": profile_data, "calorie_goal": calorie_goal}), 200

    # --- Handle POST Request ---
    elif request.method == 'POST':
        new_profile_data = request.get_json()
        required_keys = ['age', 'weight', 'height', 'gender', 'activity_level']
        if not new_profile_data or not all(key in new_profile_data for key in required_keys):
            print(f"[POST /profile] Error: Missing fields. Data: {new_profile_data}")
            return jsonify({"error": "Missing profile fields"}), 400

        print(f"[POST /profile] Received data for '{username}': {new_profile_data}")
        user_db[username]['profile'] = new_profile_data; save_user_data(user_db)
        print(f"[POST /profile] User data saved for '{username}'.")

        session['profile'] = new_profile_data # Update session profile
        calorie_goal = calculate_tdee(new_profile_data) # Recalculate goal
        session['calorie_goal'] = calorie_goal # Update session goal
        session.modified = True # Explicitly mark modified

        print(f"[POST /profile] Profile updated for '{username}'. New goal: {calorie_goal}")
        print(f"[POST /profile] Session keys after update: {list(session.keys())}, Goal: {session.get('calorie_goal')}, User: {session.get('username')}") # DEBUG
        if 'username' not in session: print("CRITICAL ERROR: Username MISSING from session after profile update!") # DEBUG

        return jsonify({"message": "Profile updated", "profile": new_profile_data, "calorie_goal": calorie_goal}), 200

# --- Prediction Endpoint ---
@app.route('/predict', methods=['POST'])
def predict():
    # Prediction logic remains the same...
    if model is None: return jsonify({"error": "Model unavailable"}), 500
    if 'image' not in request.files: return jsonify({"error": "No image file"}), 400
    file = request.files['image'];
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    if not allowed_file(file.filename): return jsonify({"error": "Invalid file type"}), 400

    filename = werkzeug.utils.secure_filename(file.filename)
    temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(temp_image_path); print(f"Image saved: {temp_image_path}")
        try: img = Image.open(temp_image_path); img.verify(); img.close(); print("Image validated.")
        except Exception as img_err: print(f"Img validation err: {img_err}"); raise ValueError("Invalid image file") from img_err

        print(f"Predicting: {temp_image_path}")
        results = model.predict(source=temp_image_path, conf=CONFIDENCE_THRESHOLD, verbose=False)

        detected_items_details = []; total_nutrition = {k: 0.0 for k in ['calories','protein','carbs','fat']}
        if results and results[0].boxes:
            for box in results[0].boxes:
                try:
                    class_id = int(box.cls[0]); confidence = float(box.conf[0])
                    if 0 <= class_id < len(food_names):
                        food_name = food_names[class_id]
                        detected_items_details.append({'food': food_name, 'confidence': round(confidence, 2)})
                        if food_name in nutrition_db: item_nutrition = nutrition_db[food_name]; [total_nutrition.update({k: total_nutrition[k] + item_nutrition.get(k,0)}) for k in total_nutrition]
                except Exception as box_err: print(f"Error processing box: {box_err}")

        for key in total_nutrition: total_nutrition[key] = round(total_nutrition[key], 1)
        print(f"Predicted Nutrition: {total_nutrition}")
        return jsonify({"detected_items": detected_items_details, "estimated_total_nutrition": total_nutrition}), 200

    except ValueError as ve: return jsonify({"error": str(ve)}), 400
    except Exception as e: print(f"Error during prediction: {e}"); return jsonify({"error": "Prediction failed."}), 500
    finally:
        if 'temp_image_path' in locals() and os.path.exists(temp_image_path):
            try: os.remove(temp_image_path); print(f"Removed temp file.")
            except Exception as rm_err: print(f"Error removing temp file: {rm_err}")


# --- Run App ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True) # Using port 8080