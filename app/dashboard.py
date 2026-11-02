from flask import Blueprint, current_app, render_template

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def dashboard():
    return render_template("dashboard.html", demo_mode=bool(current_app.config.get("DEMO_MODE")))
