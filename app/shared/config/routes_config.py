from flask import Flask

from app.shared.routes.auth import auth_route
from app.shared.routes.main import main
from app.shared.routes.robots import robot_route
from app.projects.modernisation_platform.routes.main import modernisation_platform_main


def configure_routes(app: Flask) -> None:
    app.register_blueprint(auth_route, url_prefix="/auth")
    app.register_blueprint(main)
    app.register_blueprint(robot_route)

    app.register_blueprint(
        modernisation_platform_main, url_prefix="/modernisation-platform/"
    )
