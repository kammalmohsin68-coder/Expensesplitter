from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

# MySQL Configuration for XAMPP
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Default XAMPP password is empty
app.config['MYSQL_DB'] = 'expense_splitter'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Helper function to get current user (for demo, we'll use user_id=1)
# In a real app, you'd implement login system
CURRENT_USER_ID = 1

@app.route('/')
def index():
    """Dashboard - Show current month's expenses and summary"""
    try:
        cur = mysql.connection.cursor()
        
        # Get current month's total expenses
        cur.execute("""
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE user_id = %s 
            AND MONTH(expense_date) = MONTH(CURDATE()) 
            AND YEAR(expense_date) = YEAR(CURDATE())
        """, (CURRENT_USER_ID,))
        current_month_total = cur.fetchone()['total'] or 0
        
        # Get today's expenses
        cur.execute("""
            SELECT * FROM expenses 
            WHERE user_id = %s 
            AND expense_date = CURDATE() 
            ORDER BY created_at DESC
        """, (CURRENT_USER_ID,))
        today_expenses = cur.fetchall()
        
        # Get category-wise spending for current month
        cur.execute("""
            SELECT category, SUM(amount) as total 
            FROM expenses 
            WHERE user_id = %s 
            AND MONTH(expense_date) = MONTH(CURDATE()) 
            AND YEAR(expense_date) = YEAR(CURDATE())
            GROUP BY category
            ORDER BY total DESC
        """, (CURRENT_USER_ID,))
        category_spending = cur.fetchall()
        
        # Get daily average for current month
        cur.execute("""
            SELECT AVG(daily_total) as avg_daily 
            FROM (
                SELECT SUM(amount) as daily_total 
                FROM expenses 
                WHERE user_id = %s 
                AND MONTH(expense_date) = MONTH(CURDATE()) 
                AND YEAR(expense_date) = YEAR(CURDATE())
                GROUP BY expense_date
            ) as daily_totals
        """, (CURRENT_USER_ID,))
        avg_daily = cur.fetchone()['avg_daily'] or 0
        
        # Get user info
        cur.execute("SELECT * FROM users WHERE id = %s", (CURRENT_USER_ID,))
        user = cur.fetchone()
        
        cur.close()
        
        return render_template('index.html', 
                             current_month_total=current_month_total,
                             today_expenses=today_expenses,
                             category_spending=category_spending,
                             avg_daily=avg_daily,
                             user=user,
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
            
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO expenses (user_id, expense_date, category, amount, description, paid_by, split_with)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (CURRENT_USER_ID, expense_date, category, amount, description, paid_by, split_with))
            
            mysql.connection.commit()
            cur.close()
            
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
        cur = mysql.connection.cursor()
        
        # Get filter parameters
        start_date = request.args.get('start_date', datetime.now().strftime('%Y-%m-01'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        category = request.args.get('category', '')
        
        # Build query based on filters
        query = """
            SELECT * FROM expenses 
            WHERE user_id = %s 
            AND expense_date BETWEEN %s AND %s
        """
        params = [CURRENT_USER_ID, start_date, end_date]
        
        if category and category != 'All':
            query += " AND category = %s"
            params.append(category)
        
        query += " ORDER BY expense_date DESC, created_at DESC"
        
        cur.execute(query, params)
        expenses = cur.fetchall()
        
        # Get total
        cur.execute("""
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE user_id = %s AND expense_date BETWEEN %s AND %s
        """, (CURRENT_USER_ID, start_date, end_date))
        total = cur.fetchone()['total'] or 0
        
        # Get all categories for filter dropdown
        cur.execute("SELECT DISTINCT category FROM expenses WHERE user_id = %s", (CURRENT_USER_ID,))
        categories = [cat['category'] for cat in cur.fetchall()]
        
        cur.close()
        
        return render_template('view_expenses.html', 
                             expenses=expenses, 
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
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        try:
            expense_date = request.form['expense_date']
            category = request.form['category']
            amount = float(request.form['amount'])
            description = request.form['description']
            
            cur.execute("""
                UPDATE expenses 
                SET expense_date = %s, category = %s, amount = %s, description = %s
                WHERE id = %s AND user_id = %s
            """, (expense_date, category, amount, description, expense_id, CURRENT_USER_ID))
            
            mysql.connection.commit()
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('view_expenses'))
            
        except Exception as e:
            flash(f'Error updating expense: {str(e)}', 'error')
            return redirect(url_for('edit_expense', expense_id=expense_id))
    
    # GET request - fetch expense data
    cur.execute("SELECT * FROM expenses WHERE id = %s AND user_id = %s", 
                (expense_id, CURRENT_USER_ID))
    expense = cur.fetchone()
    cur.close()
    
    if not expense:
        flash('Expense not found!', 'error')
        return redirect(url_for('view_expenses'))
    
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete_expense/<int:expense_id>')
def delete_expense(expense_id):
    """Delete an expense"""
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM expenses WHERE id = %s AND user_id = %s", 
                   (expense_id, CURRENT_USER_ID))
        mysql.connection.commit()
        cur.close()
        
        flash('Expense deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting expense: {str(e)}', 'error')
    
    return redirect(url_for('view_expenses'))

@app.route('/report')
def report():
    """Generate monthly expense report"""
    try:
        cur = mysql.connection.cursor()
        
        # Get selected month (default: current month)
        selected_month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        year, month = selected_month.split('-')
        
        # Get daily breakdown
        cur.execute("""
            SELECT expense_date, SUM(amount) as daily_total
            FROM expenses 
            WHERE user_id = %s 
            AND YEAR(expense_date) = %s 
            AND MONTH(expense_date) = %s
            GROUP BY expense_date
            ORDER BY expense_date
        """, (CURRENT_USER_ID, year, month))
        daily_breakdown = cur.fetchall()
        
        # Get category breakdown
        cur.execute("""
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses 
            WHERE user_id = %s 
            AND YEAR(expense_date) = %s 
            AND MONTH(expense_date) = %s
            GROUP BY category
            ORDER BY total DESC
        """, (CURRENT_USER_ID, year, month))
        category_breakdown = cur.fetchall()
        
        # Get monthly total
        cur.execute("""
            SELECT SUM(amount) as total, COUNT(*) as count
            FROM expenses 
            WHERE user_id = %s 
            AND YEAR(expense_date) = %s 
            AND MONTH(expense_date) = %s
        """, (CURRENT_USER_ID, year, month))
        monthly_summary = cur.fetchone()
        
        cur.close()
        
        # Generate month name
        month_name = datetime(int(year), int(month), 1).strftime('%B %Y')
        
        return render_template('report.html',
                             daily_breakdown=daily_breakdown,
                             category_breakdown=category_breakdown,
                             monthly_summary=monthly_summary,
                             month_name=month_name,
                             selected_month=selected_month)
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        return render_template('report.html')

@app.route('/api/dashboard_data')
def dashboard_data():
    """API endpoint for dashboard data (for AJAX updates)"""
    try:
        cur = mysql.connection.cursor()
        
        # Get last 7 days expenses
        cur.execute("""
            SELECT expense_date, SUM(amount) as total
            FROM expenses 
            WHERE user_id = %s 
            AND expense_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY expense_date
            ORDER BY expense_date
        """, (CURRENT_USER_ID,))
        weekly_data = cur.fetchall()
        
        cur.close()
        
        return jsonify(weekly_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)