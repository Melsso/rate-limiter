import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from rate_limiter.algorithms.base import RateLimiter
from rate_limiter.core.guard import KeyFunc
from rate_limiter.dependencies import RateLimit
from rate_limiter.keys import default_key_func

_REQUEST = "_rate_limit_request"
_RESPONSE = "_rate_limit_response"


def _find_param(params: list[inspect.Parameter], cls: type) -> str | None:
    for p in params:
        if isinstance(p.annotation, type) and issubclass(p.annotation, cls):
            return p.name
    return None


def rate_limit(
    limiter: RateLimiter,
    key_func: KeyFunc = default_key_func,
    fail_open: bool = True,
    namespace: str | None = None,
    exempt_when: Callable[[Request], bool] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    dependency = RateLimit(
        limiter,
        key_func=key_func,
        fail_open=fail_open,
        namespace=namespace,
        exempt_when=exempt_when,
    )

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        try:
            sig = inspect.signature(func, eval_str=True)
        except NameError:
            sig = inspect.signature(func)

        params = list(sig.parameters.values())
        found_request = _find_param(params, Request)
        found_response = _find_param(params, Response)
        request_name = found_request or _REQUEST
        response_name = found_response or _RESPONSE

        extra: list[inspect.Parameter] = []
        if found_request is None:
            extra.append(
                inspect.Parameter(
                    _REQUEST, inspect.Parameter.KEYWORD_ONLY, annotation=Request
                )
            )
        if found_response is None:
            extra.append(
                inspect.Parameter(
                    _RESPONSE, inspect.Parameter.KEYWORD_ONLY, annotation=Response
                )
            )

        if params and params[-1].kind is inspect.Parameter.VAR_KEYWORD:
            new_params = params[:-1] + extra + params[-1:]
        else:
            new_params = params + extra

        is_async = inspect.iscoroutinefunction(func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request = kwargs[request_name]
            response: Response = kwargs[response_name]
            if found_request is None:
                del kwargs[request_name]
            if found_response is None:
                del kwargs[response_name]

            headers = await dependency.evaluate(request, response)

            if is_async:
                result = await func(*args, **kwargs)
            else:
                result = await run_in_threadpool(func, *args, **kwargs)

            if headers and isinstance(result, Response):
                for name, value in headers.items():
                    result.headers.setdefault(name, value)
            return result

        wrapper.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]
        return wrapper

    return decorator
