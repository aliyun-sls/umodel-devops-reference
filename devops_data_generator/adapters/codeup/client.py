"""alibabacloud DevOps SDK wrapper with soft import."""

import logging

logger = logging.getLogger(__name__)

try:
    from alibabacloud_devops20210625.client import Client as DevopsClient  # type: ignore
    from alibabacloud_devops20210625 import models as devops_models  # type: ignore
    from alibabacloud_credentials.client import (  # type: ignore
        Client as CredentialClient,
        Config as CredentialConfig,
    )
    from alibabacloud_tea_openapi import models as open_api_models  # type: ignore
    from alibabacloud_tea_util import models as util_models  # type: ignore

    CODEUP_SDK_AVAILABLE = True
except ModuleNotFoundError:
    DevopsClient = None  # type: ignore
    devops_models = None  # type: ignore
    CredentialClient = None  # type: ignore
    CredentialConfig = None  # type: ignore
    open_api_models = None  # type: ignore
    util_models = None  # type: ignore
    CODEUP_SDK_AVAILABLE = False


# Fixed endpoint matching the original zip 2 implementation. The aliyun
# DevOps service is regional; Hangzhou is the documented default.
CODEUP_DEFAULT_ENDPOINT = "devops.cn-hangzhou.aliyuncs.com"


def create_codeup_client(access_key_id: str, access_key_secret: str, endpoint: str = CODEUP_DEFAULT_ENDPOINT):
    """Return an alibabacloud DevOps client or None if the SDK is missing."""
    if not CODEUP_SDK_AVAILABLE:
        logger.warning("alibabacloud-devops20210625 is not installed; codeup adapter disabled")
        return None
    cred = CredentialClient(
        CredentialConfig(
            type="access_key",
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
    )
    config = open_api_models.Config(credential=cred)
    config.endpoint = endpoint
    return DevopsClient(config)
