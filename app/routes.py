from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Mission

main = Blueprint('main', __name__)

@main.route('/client/dashboard', methods=['GET', 'POST'])
def client_dashboard():
    # ... ton code de route ici ...
