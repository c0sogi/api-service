from time import time
from re import match
from typing import Union, Tuple, Optional
from sqlalchemy.exc import OperationalError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from app.common.config import (
    Config,
    EXCEPT_PATH_LIST,
    EXCEPT_PATH_REGEX,
    SAMPLE_JWT_TOKEN,
)
from app.database.crud import get_api_key_and_owner
from app.errors import exceptions as ex
from app.errors.exceptions import APIException, SqlFailureEx
from app.models import UserToken
from app.utils.date_utils import UTC
from app.utils.logger import api_logger
from app.utils.query_utils import row_to_dict
from app.utils.encoding_and_hashing import hash_params, token_decode

config = Config.get()


async def access_control(request: Request, call_next: RequestResponseEndpoint):
    headers, cookies = request.headers, request.cookies
    url = request.url.path
    query_params = str(request.query_params)
    ip = request.client.host

    response: Optional[Response] = None
    error: Optional[Union[SqlFailureEx, APIException]] = None
    request.state.req_time = UTC.now()
    request.state.start = time()
    request.state.inspect = None
    request.state.user = None
    request.state.service = None
    request.state.ip = ip.split(",")[0] if "," in ip else ip

    if await url_pattern_check(url, EXCEPT_PATH_REGEX) or url in EXCEPT_PATH_LIST:
        response = await call_next(request)
        if url != "/":
            await api_logger(request=request, response=response)
        return response

    try:
        if url.startswith("/api/services"):  # Api-services must use session
            # [LOCAL] Validate token by headers(secret) and queries(key, timestamp) with session
            access_key, timestamp = await queries_params_to_key_and_timestamp(
                query_params
            )
            if "secret" not in headers.keys():
                raise ex.APIHeaderInvalidEx()
            request.state.user: UserToken = await validate_access_key(
                access_key,
                query_from_session=True,
                query_check=True,
                query_params=query_params,
                secret=headers["secret"],
                timestamp=timestamp,
            )

        elif url.startswith("/api"):  # Api-non-services don't use session
            # Validate token by headers(Authorization)
            if "authorization" not in headers.keys():
                raise ex.NotAuthorized()
            request.state.user: UserToken = await validate_access_key(
                headers.get("authorization")
            )

        else:  # Non-api pages with template rendering don't use session
            # Validate token by cookies(Authorization)
            if url.startswith("/test"):
                cookies["Authorization"] = SAMPLE_JWT_TOKEN
            if "Authorization" not in cookies.keys():
                raise ex.NotAuthorized()
            request.state.user: UserToken = await validate_access_key(
                cookies.get("Authorization")
            )
        response = await call_next(request)

    except Exception as exception:  # If any error occurs...
        error: Union[Exception, SqlFailureEx, APIException] = await exception_handler(
            exception
        )
        response = JSONResponse(
            status_code=error.status_code,
            content={
                "status": error.status_code,
                "msg": error.msg,
                "detail": error.detail,
                "code": error.code,
            },
        )
    finally:
        await api_logger(
            request=request,
            response=response,
            error=error,
            cookies=cookies,
            headers=dict(headers),
            query_params=query_params,
        ) if url.startswith("/api/services") or error is not None else ...
        return response


async def validate_access_key(
    access_key: str,
    query_from_session: bool = False,
    query_check: bool = False,
    secret: Optional[str] = None,
    query_params: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> UserToken:
    if query_from_session:  # Find API key from session
        matched_api_key, matched_user = await get_api_key_and_owner(
            access_key=access_key
        )
        if query_check:  # Validate queries with timestamp and secret
            if not secret == hash_params(
                qs=query_params, secret_key=matched_api_key.secret_key
            ):
                raise ex.APIHeaderInvalidEx()
            now_timestamp: int = UTC.timestamp(hour_diff=9)
            if not (now_timestamp - 10 < int(timestamp) < now_timestamp + 10):
                raise ex.APITimestampEx()
        return UserToken(**row_to_dict(matched_user))

    else:  # Decoding token access key without session
        token_info: dict = await token_decode(access_key=access_key)
        return UserToken(**token_info)


async def queries_params_to_key_and_timestamp(query_params: str) -> Tuple[str, str]:
    try:
        qs_dict = {
            qs_split.split("=")[0]: qs_split.split("=")[1]
            for qs_split in query_params.split("&")
        }
    except Exception:
        raise ex.APIQueryStringEx()
    if "key" not in qs_dict.keys() or "timestamp" not in qs_dict.keys():
        raise ex.APIQueryStringEx()
    return qs_dict["key"], qs_dict["timestamp"]


async def url_pattern_check(path: str, pattern: str) -> bool:
    return True if match(pattern, path) else False


async def exception_handler(error: Exception) -> Union[SqlFailureEx, APIException]:
    if isinstance(error, OperationalError):
        return SqlFailureEx(ex=error)
    elif isinstance(error, APIException):
        return error
    else:
        return APIException(ex=error, detail=str(error))
