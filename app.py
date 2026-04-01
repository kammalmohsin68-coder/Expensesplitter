from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Database configuration - SQLite (no XAMPP needed!)
DATABASE = 'expense_splitter.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def init_db():
    """Initialize database with tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            room_number TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create expenses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            expense_date DATE NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            paid_by TEXT DEFAULT 'self',
            split_with TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create daily_mess table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_mess (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date DATE NOT NULL,
            meal_type TEXT CHECK(meal_type IN ('breakfast', 'lunch', 'dinner')) NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            cost_per_item REAL NOT NULL,
            total_cost REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert sample data if users table is empty
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()['count'] == 0:
        cursor.execute("INSERT INTO users (username, email, room_number) VALUES (?, ?, ?)",
                      ('john_doe', 'john@example.com', 'A-101'))
        cursor.execute("INSERT INTO users (username, email, room_number) VALUES (?, ?, ?)",
                      ('jane_smith', 'jane@example.com', 'A-102'))
        
        cursor.execute("INSERT INTO expenses (user_id, expense_date, category, amount, description) VALUES (?, ?, ?, ?, ?)",
                      (1, datetime.now().strftime('%Y-%m-%d'), 'Food', 250.00, 'Lunch at canteen'))
        cursor.execute("INSERT INTO expenses (user_id, expense_date, category, amount, description) VALUES (?, ?, ?, ?, ?)",
                      (1, datetime.now().strftime('%Y-%m-%d'), 'Groceries', 500.00, 'Monthly groceries'))
    
    conn.commit()
    conn.close()

# Helper function to get current user
CURRENT_USER_ID = 1

@app.route('/')
def index():
    """Dashboard - Show current month's expenses and summary"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get current month's total expenses
        cursor.execute("""
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE user_id = ? 
            AND strftime('%m', expense_date) = strftime('%m', 'now')
            AND strftime('%Y', expense_date) = strftime('%Y', 'now')
        """, (CURRENT_USER_ID,))
        result = cursor.fetchone()
        current_month_total = result['total'] if result['total'] else 0
        
        # Get today's expenses
        cursor.execute("""
            SELECT * FROM expenses 
            WHERE user_id = ? 
            AND expense_date = date('now')
            ORDER BY created_at DESC
        """, (CURRENT_USER_ID,))
        today_expenses = cursor.fetchall()
        
        # Get category-wise spending for current month
        cursor.execute("""
            SELECT category, SUM(amount) as total 
            FROM expenses 
            WHERE user_id = ? 
            AND strftime('%m', expense_date) = strftime('%m', 'now')
            AND strftime('%Y', expense_date) = strftime('%Y', 'now')
            GROUP BY category
            ORDER BY total DESC
        """, (CURRENT_USER_ID,))
        category_spending = cursor.fetchall()
        
        # Get daily average for current month
        cursor.execute("""
            SELECT AVG(daily_total) as avg_daily 
            FROM (
                SELECT SUM(amount) as daily_total 
                FROM expenses 
                WHERE user_id = ? 
                AND strftime('%m', expense_date) = strftime('%m', 'now')
                AND strftime('%Y', expense_date) = strftime('%Y', 'now')
                GROUP BY expense_date
            ) as daily_totals
        """, (CURRENT_USER_ID,))
        result = cursor.fetchone()
        avg_daily = result['avg_daily'] if result['avg_daily'] else 0
        
        # Get user info
        cursor.execute("SELECT * FROM users WHERE id = ?", (CURRENT_USER_ID,))
        user = cursor.fetchone()
        
        conn.close()
        
        # Convert Row objects to dictionaries for template
        today_expenses_list = [dict(expense) for expense in today_expenses]
        category_spending_list = [dict(cat) for cat in category_spending]
        
        return render_template('index.html', 
                             current_month_total=current_month_total,
                             today_expenses=today_expenses_list,
                             category_spending=category_spending_list,
                             avg_daily=avg_daily,
                             user=dict(user) if user else None,
                             datetime=datetime)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return render_template('index.html', today_expenses=[])

@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    """Add a new expense"""
    if request.method == 'POST':
        try:
            expense_date = request.form['expense_date']
            category = request.form['category']
            amount = float(request.form['amount'])
            description = request.form['description']
            paid_by = request.form.get('paid_by', 'self')
            split_with = request.form.get('split_with', '')
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO expenses (user_id, expense_date, category, amount, description, paid_by, split_with)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (CURRENT_USER_ID, expense_date, category, amount, description, paid_by, split_with))
            
            conn.commit()
            conn.close()
            
            flash('Expense added successfully!', 'success')
            return redirect(url_for('view_expenses'))
            
        except Exception as e:
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('add_expense'))
    
    return render_template('add_expense.html')

@app.route('/view_expenses')
def view_expenses():
    """View all expenses with filters"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get filter parameters
        start_date = request.args.get('start_date', datetime.now().strftime('%Y-%m-01'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        category = request.args.get('category', '')
        
        # Build query based on filters
        query = """
            SELECT * FROM expenses 
            WHERE user_id = ? 
            AND expense_date BETWEEN ? AND ?
        """
        params = [CURRENT_USER_ID, start_date, end_date]
        
        if category and category != 'All':
            query += " AND category = ?"
            params.append(category)
        
        query += " ORDER BY expense_date DESC, created_at DESC"
        
        cursor.execute(query, params)
        expenses = cursor.fetchall()
        
        # Get total
        cursor.execute("""
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE user_id = ? AND expense_date BETWEEN ? AND ?
        """, (CURRENT_USER_ID, start_date, end_date))
        result = cursor.fetchone()
        total = result['total'] if result['total'] else 0
        
        # Get all categories for filter dropdown
        cursor.execute("SELECT DISTINCT category FROM expenses WHERE user_id = ?", (CURRENT_USER_ID,))
        categories = [cat['category'] for cat in cursor.fetchall()]
        
        conn.close()
        
        # Convert to list of dicts
        expenses_list = [dict(expense) for expense in expenses]
        
        return render_template('view_expenses.html', 
                             expenses=expenses_list, 
                             total=total,
                             categories=categories,
                             start_date=start_date,
                             end_date=end_date)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return render_template('view_expenses.html', expenses=[])

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    """Edit an existing expense"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        try:
            expense_date = request.form['expense_date']
            category = request.form['category']
            amount = float(request.form['amount'])
            description = request.form['description']
            
            cursor.execute("""
                UPDATE expenses 
                SET expense_date = ?, category = ?, amount = ?, description = ?
                WHERE id = ? AND user_id = ?
            """, (expense_date, category, amount, description, expense_id, CURRENT_USER_ID))
            
            conn.commit()
            conn.close()
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('view_expenses'))
            
        except Exception as e:
            flash(f'Error updating expense: {str(e)}', 'error')
            return redirect(url_for('edit_expense', expense_id=expense_id))
    
    # GET request - fetch expense data
    cursor.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", 
                  (expense_id, CURRENT_USER_ID))
    expense = cursor.fetchone()
    conn.close()
    
    if not expense:
        flash('Expense not found!', 'error')
        return redirect(url_for('view_expenses'))
    
    return render_template('edit_expense.html', expense=dict(expense))

@app.route('/delete_expense/<int:expense_id>')
def delete_expense(expense_id):
    """Delete an expense"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", 
                      (expense_id, CURRENT_USER_ID))
        conn.commit()
        conn.close()
        
        flash('Expense deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting expense: {str(e)}', 'error')
    
    return redirect(url_for('view_expenses'))

@app.route('/report')
def report():
    """Generate monthly expense report"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get selected month (default: current month)
        selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        year, month = selected_month.split('-')
        
        # Get daily breakdown
        cursor.execute("""
            SELECT expense_date, SUM(amount) as daily_total
            FROM expenses 
            WHERE user_id = ? 
            AND strftime('%Y', expense_date) = ? 
            AND strftime('%m', expense_date) = ?
            GROUP BY expense_date
            ORDER BY expense_date
        """, (CURRENT_USER_ID, year, month))
        daily_breakdown = cursor.fetchall()
        
        # Get category breakdown
        cursor.execute("""
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses 
            WHERE user_id = ? 
            AND strftime('%Y', expense_date) = ? 
            AND strftime('%m', expense_date) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (CURRENT_USER_ID, year, month))
        category_breakdown = cursor.fetchall()
        
        # Get monthly total
        cursor.execute("""
            SELECT SUM(amount) as total, COUNT(*) as count
            FROM expenses 
            WHERE user_id = ? 
            AND strftime('%Y', expense_date) = ? 
            AND strftime('%m', expense_date) = ?
        """, (CURRENT_USER_ID, year, month))
        monthly_summary = cursor.fetchone()
        
        conn.close()
        
        # Convert to dicts
        daily_list = [dict(day) for day in daily_breakdown]
        category_list = [dict(cat) for cat in category_breakdown]
        monthly_dict = dict(monthly_summary) if monthly_summary else {'total': 0, 'count': 0}
        
        # Generate month name
        month_name = datetime(int(year), int(month), 1).strftime('%B %Y')
        
        return render_template('report.html',
                             daily_breakdown=daily_list,
                             category_breakdown=category_list,
                             monthly_summary=monthly_dict,
                             month_name=month_name,
                             selected_month=selected_month)
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        return render_template('report.html')

@app.route('/api/dashboard_data')
def dashboard_data():
    """API endpoint for dashboard data"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get last 7 days expenses
        cursor.execute("""
            SELECT expense_date, SUM(amount) as total
            FROM expenses 
            WHERE user_id = ? 
            AND expense_date >= date('now', '-7 days')
            GROUP BY expense_date
            ORDER BY expense_date
        """, (CURRENT_USER_ID,))
        weekly_data = cursor.fetchall()
        conn.close()
        
        return jsonify([dict(row) for row in weekly_data])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Initialize database when app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
