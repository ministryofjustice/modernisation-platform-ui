import logging

from app.app import create_app
from app.projects.aws_account_standards.services.AwsService import AwsService
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main():
    configure_logging(app_config.logging_level)
    logger.info("Running...")

    aws_service = AwsService()
    aws_service.log_base_session_and_mp_scanner_role_session_for_account(
        app_config.aws.cooker_account_id
    )

    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
