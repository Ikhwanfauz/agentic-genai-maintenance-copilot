import logging
from collections.abc import (
    AsyncIterator,
    Callable,
)
from contextlib import (
    AbstractContextManager,
    asynccontextmanager,
)
from threading import Lock

from fastapi import FastAPI

from app.agent.runtime import (
    AgentRuntime,
    open_agent_runtime,
)
from app.api.routes.agent import router as agent_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings)

logger = logging.getLogger(__name__)

AgentRuntimeFactory = Callable[
    [],
    AbstractContextManager[AgentRuntime],
]


def create_default_agent_runtime() -> AbstractContextManager[AgentRuntime]:
    return open_agent_runtime(settings)


@asynccontextmanager
async def lifespan(
    application: FastAPI,
) -> AsyncIterator[None]:
    logger.info("Application starting")

    try:
        yield
    finally:
        runtime_context = getattr(
            application.state,
            "agent_runtime_context",
            None,
        )

        if runtime_context is not None:
            runtime_context.__exit__(
                None,
                None,
                None,
            )
            application.state.agent_runtime_context = None
            application.state.agent_graph = None

        logger.info("Application shutting down")


def create_app(
    *,
    runtime_factory: AgentRuntimeFactory | None = None,
) -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.state.agent_graph = None
    application.state.agent_runtime_context = None
    application.state.agent_runtime_factory = runtime_factory or create_default_agent_runtime
    application.state.agent_runtime_lock = Lock()

    application.include_router(health_router)
    application.include_router(agent_router)

    return application


app = create_app()
