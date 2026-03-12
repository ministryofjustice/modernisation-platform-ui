import logging
from flask import Blueprint, render_template

from app.shared.middleware.auth import requires_auth

logger = logging.getLogger(__name__)

aws_account_standards_main = Blueprint("aws_account_standards_main", __name__)


@aws_account_standards_main.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template("projects/aws_account_standards/pages/home.html")


@aws_account_standards_main.route("/poc-report", methods=["GET"])
def poc_report():
    return render_template("projects/aws_account_standards/pages/poc_report.html")
