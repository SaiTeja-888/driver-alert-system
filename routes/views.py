from flask import Blueprint, render_template

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@views_bp.route('/live')
def live():
    return render_template('live.html', active_page='live')

@views_bp.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')

@views_bp.route('/reports')
def reports():
    return render_template('reports.html', active_page='reports')

@views_bp.route('/settings')
def settings():
    return render_template('settings.html', active_page='settings')
