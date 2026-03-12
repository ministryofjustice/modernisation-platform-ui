from flask import Flask

from app.shared.routes.auth import auth_route
from app.shared.routes.main import main
from app.shared.routes.robots import robot_route
from app.projects.reports.routes.main import reports_main
from app.projects.aws_account_standards.routes.main import aws_account_standards_main


def configure_routes(app: Flask) -> None:
    app.register_blueprint(auth_route, url_prefix="/auth")
    app.register_blueprint(main)
    app.register_blueprint(robot_route)

    app.register_blueprint(reports_main, url_prefix="/reports")
    app.register_blueprint(
        aws_account_standards_main, url_prefix="/aws-account-standards"
    )
