from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from calendar import monthrange, TextCalendar
import calendar
import random
import re
from pytz import timezone

app = Flask(__name__)
app.secret_key = "secretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calendar.db'
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    task_date = db.Column(db.String(10), nullable=False)
    task_time = db.Column(db.String(5), nullable=False)  # if not already added
    task_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)

class TipQuote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(200), nullable=False)
    tip = db.Column(db.Text, nullable=False)
    quote = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=True)

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Query tasks ordered by date, then time
    tasks = Task.query.filter_by(user_id=session['user_id']).order_by(Task.task_date, Task.task_time).all()

    task_dict = {}
    for task in tasks:
        task_dict.setdefault(task.task_date, []).append(task)

    # Fetch unique task names from TipQuote table
    task_names = db.session.query(TipQuote.task_name).distinct().all()
    task_names = [name[0] for name in task_names]

    return render_template('calendar.html', task_dict=task_dict, task_names=task_names)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            return "User already exists"

        # Use compatible method for hashing
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check password format (5–8 chars and at least one digit)
        password_format_valid = 5 <= len(password) <= 8 and re.search(r'\d', password)

        if not password_format_valid:
            error = "Password must be 5–8 characters long and include at least one number."
        else:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                session['user_id'] = user.id
                return redirect(url_for('index'))
            else:
                error = "Incorrect email or password."

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/add_task', methods=['POST'])
def add_task():
    task_name = request.form['task_name']
    task_date = request.form['task_date']
    task_time = request.form['task_time']
    description = request.form['description']

    # Combine date and time into a datetime string
    task_datetime_str = f"{task_date} {task_time}"
    
    # Define your local timezone (e.g., India Standard Time)
    local_tz = timezone('Asia/Kolkata')  # Change if your location is different

    try:
        # Parse and localize task datetime
        naive_task_datetime = datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")
        task_datetime = local_tz.localize(naive_task_datetime)

        # Get current time in the same timezone
        now = datetime.now(local_tz)

        # Compare task time with now
        if task_datetime < now:
            flash("Cannot add a task in the past. Please select a valid date and time.", "error")
            return redirect(url_for('index'))

        # Create and save the task
        new_task = Task(
            user_id=session['user_id'],
            task_name=task_name,
            task_date=task_date,
            task_time=task_time,
            description=description
        )
        db.session.add(new_task)
        db.session.commit()

        flash("Task added successfully!", "success")
        return redirect(url_for('index'))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('index'))


@app.route('/generate_today_tip_quote', methods=['POST'])
def generate_today_tip_quote():
    selected_task = request.form['selected_task']
    tip_quotes = TipQuote.query.filter_by(task_name=selected_task).all()
    if tip_quotes:
        chosen = random.choice(tip_quotes)
        tip = chosen.tip
        quote = chosen.quote
        author = chosen.author  # Assuming you have this field
    else:
        tip = "No tip available."
        quote = "No quote available."
        author = ""
    return render_template('tip_quote.html', task=selected_task, tip=tip, quote=quote, author=author)

@app.route('/visualise')
def visualise():
    # Get year and month from query params, default to current month
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)

    # Get all tasks for the user in that month
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    # Fetch tasks in the specified month
    tasks = Task.query.filter(
        Task.user_id == user_id,
        Task.task_date.between(f"{year}-{month:02d}-01", f"{year}-{month:02d}-31")
    ).all()

    # Organize tasks by day (extract day from task_date)
    tasks_by_day = {}
    for task in tasks:
        day = int(task.task_date.split('-')[2])
        tasks_by_day.setdefault(day, []).append(task)

    # Get calendar weeks for the month (list of lists for weeks)
    cal = calendar.Calendar(firstweekday=0)  # Monday as first day
    month_weeks = list(cal.monthdayscalendar(year, month))

    return render_template(
        'visualise.html',
        year=year,
        month=month,
        tasks_by_day=tasks_by_day,
        month_weeks=month_weeks
    )

@app.route('/delete_task', methods=['POST'])
def delete_task():
    task_id = request.form.get('task_id')
    task = Task.query.get(task_id)

    if task and task.user_id == session.get('user_id'):
        db.session.delete(task)
        db.session.commit()
    
    return redirect(url_for('index'))

# CLI to create tables and preload
@app.cli.command("initdb")
def initdb():
    db.create_all()
    tips_and_quotes = {
       "Study": [
        ("Break study sessions into focused 25-minute chunks using the Pomodoro Technique, and take 5-minute breaks to rest your brain.", 
         "Success is no accident.", "Pele"),
        ("Summarize what you’ve just studied in your own words to reinforce understanding and retention.", 
         "Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
        ("Instead of re-reading, test yourself regularly to improve long-term recall.", 
         "An investment in knowledge pays the best interest.", "Benjamin Franklin")
    ],
    "Workout": [
        ("Begin your day with light cardio or stretching to energize your body and improve circulation.", 
         "The body achieves what the mind believes.", "Unknown"),
        ("Set realistic fitness goals and track your progress weekly to stay motivated and consistent.", 
         "Strength doesn’t come from what you can do. It comes from overcoming the things you once thought you couldn’t.", "Rikki Rogers"),
        ("Incorporate recovery days to prevent burnout and injuries—your body grows during rest.", 
         "The difference between try and triumph is a little 'umph'.", "Marvin Phillips")
    ],
    "Read": [
        ("Choose a dedicated time daily for reading, free from distractions like phones or noise.", 
         "A reader lives a thousand lives before he dies. The man who never reads lives only one.", "George R.R. Martin"),
        ("Pause occasionally to reflect on key ideas and connect them to your own life experiences.", 
         "Reading is essential for those who seek to rise above the ordinary.", "Jim Rohn"),
        ("Create a reading journal to track your favorite quotes, characters, or summaries.", 
         "Once you learn to read, you will be forever free.", "Frederick Douglass")
    ],
    "Meditate": [
        ("Start your mornings with 5–10 minutes of guided meditation to center your thoughts before the day begins.", 
         "You should sit in meditation for twenty minutes every day—unless you’re too busy; then you should sit for an hour.", "Zen Proverb"),
        ("Use body scans or breathing techniques to bring awareness to your physical and mental state.", 
         "The thing about meditation is: You become more and more you.", "David Lynch"),
        ("Don’t resist thoughts; notice them, then gently bring your attention back to the breath.", 
         "Quiet the mind, and the soul will speak.", "Ma Jaya Sati Bhagavati")
    ],
    "Write": [
        ("Start a daily journal or blog, even if it’s just a few lines. Regular writing clarifies thoughts and builds confidence.", 
         "There is no greater agony than bearing an untold story inside you.", "Maya Angelou"),
        ("Focus on the message before perfection—write freely, then refine your work later during editing.", 
         "Start writing, no matter what. The water does not flow until the faucet is turned on.", "Louis L’Amour"),
        ("Expose yourself to diverse writing styles and genres to enrich your own voice and creativity.", 
         "If you want to change the world, pick up your pen and write.", "Martin Luther")
    ],
    "Code": [
        ("Before jumping into code, plan your logic with pseudocode or flowcharts—it saves time and confusion.", 
         "Programs must be written for people to read, and only incidentally for machines to execute.", "Harold Abelson"),
        ("Tackle coding problems daily, even for 20 minutes, to sharpen your thinking like a muscle.", 
         "Code is like humor. When you have to explain it, it’s bad.", "Cory House"),
        ("Read open-source projects and contribute to them to learn real-world practices.", 
         "The only way to learn a new programming language is by writing programs in it.", "Dennis Ritchie")
    ],
    "Organize": [
        ("At the start of each day, write down your top 3 priorities and schedule them on a calendar.", 
         "For every minute spent organizing, an hour is earned.", "Benjamin Franklin"),
        ("Use digital tools like Trello or Notion to manage projects and reduce mental clutter.", 
         "Outer order contributes to inner calm.", "Gretchen Rubin"),
        ("Group similar tasks and batch them together to minimize context switching.", 
         "Being organized isn’t about being perfect. It’s about being efficient.", "Unknown")
    ],
    "Cook": [
        ("Prep ingredients before cooking to stay focused and enjoy the process. Cooking becomes meditative when planned.", 
         "Cooking is at once child’s play and adult joy. And cooking done with care is an act of love.", "Craig Claiborne"),
        ("Experiment with new recipes once a week to keep meals exciting and expand your skills.", 
         "One cannot think well, love well, sleep well, if one has not dined well.", "Virginia Woolf"),
        ("Use fresh herbs and spices to elevate the simplest dishes into something memorable.", 
         "You don’t have to cook fancy or complicated masterpieces — just good food from fresh ingredients.", "Julia Child")
    ],
    "Clean": [
        ("Use the 10-minute rule: clean for just 10 minutes, and you’ll likely keep going.", 
         "Cleanliness is next to godliness.", "John Wesley"),
        ("Declutter one drawer or corner each day to avoid overwhelming cleanups.", 
         "Outer order brings inner peace.", "Gretchen Rubin"),
        ("Play your favorite playlist or podcast while cleaning to turn it into a fun ritual.", 
         "The objective of cleaning is not just to clean, but to feel happiness living within that environment.", "Marie Kondo")
    ],
    "Plan": [
        ("Plan your week every Sunday evening—it gives structure and reduces anxiety.", 
         "A goal without a plan is just a wish.", "Antoine de Saint-Exupéry"),
        ("Time-block your calendar for deep work, errands, and breaks to maintain energy and focus.", 
         "Plans are nothing; planning is everything.", "Dwight D. Eisenhower"),
        ("Review your progress daily and adjust your priorities to stay aligned with your long-term goals.", 
         "Failing to plan is planning to fail.", "Alan Lakein")
    ],
    "Reflect": [
        ("Write down three things you're grateful for each night to end your day with a positive mindset.", 
         "We do not learn from experience... we learn from reflecting on experience.", "John Dewey"),
        ("Revisit your journal weekly to observe patterns, progress, and personal growth.", 
         "The unexamined life is not worth living.", "Socrates"),
        ("Ask yourself empowering questions like 'What went well today?' and 'What can I improve tomorrow?'", 
         "Reflection is one of the most underused yet powerful tools for success.", "Richard Carlson")
    ]
}

    for task, entries in tips_and_quotes.items():
        for tip, quote, author in entries:
            db.session.add(TipQuote(task_name=task, tip=tip, quote=quote, author=author))

    db.session.commit()
    print("Database initialized with grouped tips and quotes.")
    
if __name__ == '__main__':
    app.run(debug=True)
