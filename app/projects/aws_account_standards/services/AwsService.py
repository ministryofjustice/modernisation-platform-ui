from __future__ import annotations

import logging
from typing import cast

from boto3 import Session
from botocore.config import Config
from mypy_boto3_sts.client import STSClient

logger = logging.getLogger(__name__)


class AwsService:
    def __init__(self, default_region_name: str = "eu-west-2") -> None:
        self.__default_region_name = default_region_name
        self.__mp_aws_account_standards_scanner_role_name = (
            "mp-aws-account-standards-scanner-role"
        )

    def __get_base_session(self) -> Session:
        return Session(region_name=self.__default_region_name)

    def __assume_role(
        self,
        session: Session,
        role_arn: str,
        session_name: str = "modernisation-platform-aws-account-standards",
    ) -> Session:
        sts_client = self.__get_sts_client(session)
        response = sts_client.assume_role(
            RoleArn=role_arn, RoleSessionName=session_name
        )
        credentials = response["Credentials"]
        return Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=self.__default_region_name,
        )

    def __get_sts_client(self, session: Session) -> STSClient:
        sts_client = session.client("sts", config=Config(retries={"max_attempts": 3}))
        return cast(STSClient, sts_client)

    def __assume_mp_scanner_role(self, session: Session, account_id: str) -> Session:
        role_arn = f"arn:aws:iam::{account_id}:role/{self.__mp_aws_account_standards_scanner_role_name}"
        return self.__assume_role(
            session,
            role_arn,
            session_name="modernisation-platform-aws-account-standards-scanner",
        )

    def __log_session_identiy(self, session: Session) -> None:
        sts_client = self.__get_sts_client(session)
        identity = sts_client.get_caller_identity()
        logger.info(
            "identity: account=%s arn=%s userid=%s",
            identity.get("Account"),
            identity.get("Arn"),
            identity.get("UserId"),
        )

    def log_base_session_and_mp_scanner_role_session_for_account(
        self, account_id: str
    ) -> None:
        base_session = self.__get_base_session()
        self.__log_session_identiy(base_session)

        mp_scanner_role_session = self.__assume_mp_scanner_role(
            base_session, account_id=account_id
        )
        self.__log_session_identiy(mp_scanner_role_session)
