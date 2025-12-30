from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g
import sqlite3
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = 'timeflow_secret_key'
DATABASE = 'database.db'

# Hàm kết nối database
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Khởi tạo database
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Bảng công việc
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                created_date DATE DEFAULT (date('now')),
                due_date DATE NOT NULL,
                due_time TEXT,
                category_id INTEGER,
                status TEXT DEFAULT 'pending',
                user_id INTEGER DEFAULT 1,
                completed_date DATE,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')
        
        # Bảng phân loại
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT DEFAULT '#3498db',
                user_id INTEGER DEFAULT 1
            )
        ''')
        
        # Bảng sự kiện lịch
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_datetime DATETIME NOT NULL,
                end_datetime DATETIME,
                description TEXT,
                task_id INTEGER,
                user_id INTEGER DEFAULT 1,
                share_code TEXT UNIQUE,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        ''')
        
        # Bảng cài đặt thông báo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                deadline_notification BOOLEAN DEFAULT 1,
                email_notification BOOLEAN DEFAULT 0,
                push_notification BOOLEAN DEFAULT 1,
                reminder_time INTEGER DEFAULT 1,
                sound TEXT DEFAULT 'default',
                volume INTEGER DEFAULT 70
            )
        ''')
        
        # Chèn dữ liệu mẫu
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO categories (name, color) VALUES (?, ?)",
                [('Học tập', '#e74c3c'), ('Cá nhân', '#2ecc71'), ('Công việc', '#3498db')]
            )
            
        cursor.execute("SELECT COUNT(*) FROM notifications")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO notifications (user_id) VALUES (1)"
            )
        
        db.commit()

# ========== ROUTES ==========

# Trang chính (Ảnh 1)
@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()
    
    # Lấy công việc hôm nay
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE due_date = ? 
        AND status != 'completed'
        ORDER BY due_time ASC
    ''', (today,))
    today_tasks = cursor.fetchall()
    
    # Lấy công việc sắp tới (7 ngày tới)
    next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE due_date BETWEEN ? AND ?
        AND status != 'completed'
        ORDER BY due_date ASC, due_time ASC
    ''', (today, next_week))
    upcoming_tasks = cursor.fetchall()
    
    # Thống kê
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
    pending_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'")
    in_progress_count = cursor.fetchone()[0]
    
    return render_template('index.html', 
                         today_tasks=today_tasks,
                         upcoming_tasks=upcoming_tasks,
                         pending_count=pending_count,
                         in_progress_count=in_progress_count)

# Trang tạo công việc mới (Ảnh 2)
@app.route('/create-task', methods=['GET', 'POST'])
def create_task():
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        due_date = request.form['due_date']
        due_time = request.form.get('due_time', '')
        category_id = request.form.get('category_id', 1)
        
        cursor.execute('''
            INSERT INTO tasks (title, description, due_date, due_time, category_id, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (title, description, due_date, due_time, category_id))
        db.commit()
        
        return redirect(url_for('track_tasks'))
    
    # Lấy danh sách phân loại
    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()
    
    return render_template('create_task.html', categories=categories)

# Quản lý phân loại (Ảnh 3)
@app.route('/manage-categories', methods=['GET', 'POST'])
def manage_categories():
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form['name']
            color = request.form.get('color', '#3498db')
            cursor.execute('INSERT INTO categories (name, color) VALUES (?, ?)', (name, color))
        elif action == 'delete':
            category_id = request.form['category_id']
            cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        
        db.commit()
        return redirect(url_for('manage_categories'))
    
    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()
    
    return render_template('manage_categories.html', categories=categories)

# Theo dõi công việc (Ảnh 4)
@app.route('/track-tasks')
def track_tasks():
    db = get_db()
    cursor = db.cursor()
    
    # Lọc theo trạng thái
    status_filter = request.args.get('status', 'all')
    
    query = "SELECT t.*, c.name as category_name FROM tasks t LEFT JOIN categories c ON t.category_id = c.id"
    
    if status_filter == 'pending':
        query += " WHERE t.status = 'pending'"
    elif status_filter == 'in_progress':
        query += " WHERE t.status = 'in_progress'"
    elif status_filter == 'completed':
        query += " WHERE t.status = 'completed'"
    
    query += " ORDER BY t.due_date ASC, t.due_time ASC"
    
    cursor.execute(query)
    tasks = cursor.fetchall()
    
    # Thống kê
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
    pending_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'")
    in_progress_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
    completed_count = cursor.fetchone()[0]
    
    return render_template('track_tasks.html', 
                         tasks=tasks,
                         pending_count=pending_count,
                         in_progress_count=in_progress_count,
                         completed_count=completed_count,
                         status_filter=status_filter)

# Cập nhật trạng thái công việc
@app.route('/update-task-status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    db = get_db()
    cursor = db.cursor()
    
    status = request.json.get('status')
    
    if status == 'completed':
        completed_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE tasks 
            SET status = ?, completed_date = ?
            WHERE id = ?
        ''', (status, completed_date, task_id))
    else:
        cursor.execute('UPDATE tasks SET status = ? WHERE id = ?', (status, task_id))
    
    db.commit()
    return jsonify({'success': True})

# Lịch cá nhân (Ảnh 5)
@app.route('/calendar')
def calendar():
    db = get_db()
    cursor = db.cursor()
    
    # Lấy tháng và năm từ query param
    month = request.args.get('month', datetime.now().month)
    year = request.args.get('year', datetime.now().year)
    
    # Lấy sự kiện trong tháng
    start_date = f"{year}-{int(month):02d}-01"
    if int(month) == 12:
        end_date = f"{int(year)+1}-01-01"
    else:
        end_date = f"{year}-{int(month)+1:02d}-01"
    
    cursor.execute('''
        SELECT * FROM events 
        WHERE start_datetime >= ? AND start_datetime < ?
        ORDER BY start_datetime ASC
    ''', (start_date, end_date))
    events = cursor.fetchall()
    
    # Lấy các công việc có deadline trong tháng
    cursor.execute('''
        SELECT t.*, c.name as category_name FROM tasks t 
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE due_date >= ? AND due_date < ?
        ORDER BY due_date ASC, due_time ASC
    ''', (start_date, end_date))
    tasks = cursor.fetchall()
    
    return render_template('calendar.html', 
                         events=events, 
                         tasks=tasks,
                         month=month, 
                         year=year)

# Lấy công việc theo ngày
@app.route('/get-tasks-by-date/<date>')
def get_tasks_by_date(date):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT t.*, c.name as category_name FROM tasks t 
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE due_date = ?
        ORDER BY due_time ASC
    ''', (date,))
    
    tasks = cursor.fetchall()
    result = []
    for task in tasks:
        result.append(dict(task))
    
    return jsonify(result)

# Tạo mã chia sẻ lịch
@app.route('/create-share-code', methods=['POST'])
def create_share_code():
    import secrets
    db = get_db()
    cursor = db.cursor()
    
    share_code = secrets.token_urlsafe(8)
    
    cursor.execute('''
        INSERT INTO events (title, start_datetime, share_code, user_id)
        VALUES (?, ?, ?, 1)
    ''', ('Shared Calendar', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), share_code))
    
    db.commit()
    return jsonify({'share_code': share_code})

# Cài đặt thông báo (Ảnh 6)
@app.route('/notifications', methods=['GET', 'POST'])
def notifications():
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        deadline_notification = 1 if request.form.get('deadline_notification') else 0
        email_notification = 1 if request.form.get('email_notification') else 0
        push_notification = 1 if request.form.get('push_notification') else 0
        reminder_time = request.form.get('reminder_time', 1)
        sound = request.form.get('sound', 'default')
        volume = request.form.get('volume', 70)
        
        cursor.execute('''
            UPDATE notifications 
            SET deadline_notification = ?, 
                email_notification = ?, 
                push_notification = ?, 
                reminder_time = ?, 
                sound = ?, 
                volume = ?
            WHERE user_id = 1
        ''', (deadline_notification, email_notification, push_notification, 
              reminder_time, sound, volume))
        db.commit()
        
        return redirect(url_for('notifications'))
    
    cursor.execute("SELECT * FROM notifications WHERE user_id = 1")
    notification_settings = cursor.fetchone()
    
    return render_template('notifications.html', settings=notification_settings)

# Thống kê (Ảnh 7)
@app.route('/statistics')
def statistics():
    db = get_db()
    cursor = db.cursor()
    
    period = request.args.get('period', 'week')  # day, week, month, year
    
    # Tính toán ngày bắt đầu theo period
    end_date = datetime.now()
    if period == 'day':
        start_date = end_date - timedelta(days=1)
    elif period == 'week':
        start_date = end_date - timedelta(days=7)
    elif period == 'month':
        start_date = end_date - timedelta(days=30)
    else:  # year
        start_date = end_date - timedelta(days=365)
    
    # Lấy dữ liệu thống kê
    cursor.execute('''
        SELECT 
            COUNT(*) as total_tasks,
            SUM(CASE WHEN completed_date <= due_date THEN 1 ELSE 0 END) as completed_early,
            SUM(CASE WHEN completed_date > due_date THEN 1 ELSE 0 END) as completed_late
        FROM tasks 
        WHERE status = 'completed' 
        AND completed_date BETWEEN ? AND ?
    ''', (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
    
    stats = cursor.fetchone()
    
    # Dữ liệu mẫu cho biểu đồ
    chart_data = {
        'labels': ['Hoàn thành sớm', 'Hoàn thành muộn', 'Chưa hoàn thành'],
        'datasets': [{
            'data': [
                stats['completed_early'] or 0,
                stats['completed_late'] or 0,
                (stats['total_tasks'] or 0) - ((stats['completed_early'] or 0) + (stats['completed_late'] or 0))
            ],
            'backgroundColor': ['#2ecc71', '#e74c3c', '#95a5a6']
        }]
    }
    
    return render_template('statistics.html', 
                         stats=stats,
                         chart_data=json.dumps(chart_data),
                         period=period)
# Trong app.py, thêm route sau vào phần routes:

@app.route('/delete-category/<int:category_id>')
def delete_category(category_id):
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Kiểm tra xem có công việc nào đang sử dụng category này không
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE category_id = ?", (category_id,))
        task_count = cursor.fetchone()[0]
        
        if task_count > 0:
            flash(f'Không thể xóa phân loại vì có {task_count} công việc đang sử dụng.', 'error')
        else:
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            db.commit()
            flash('Đã xóa phân loại thành công!', 'success')
            
    except Exception as e:
        db.rollback()
        flash('Có lỗi xảy ra khi xóa phân loại.', 'error')
    
    return redirect(url_for('manage_categories'))

# Thêm vào imports ở đầu file:
from flask import flash

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)