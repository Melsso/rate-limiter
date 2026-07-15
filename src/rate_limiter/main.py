from fastapi import FastAPI

from rate_limiter.core.container import limiter
from rate_limiter.middleware import RateLimitMiddleware

app = FastAPI()
app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}
