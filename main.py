# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Example: adk-celery-broker with injectable task store and session service.

Replace the stub classes below with your real ADK BaseAgent and
BaseSessionService subclasses, and your own BaseA2aTaskStore implementation
backed by a database (Postgres, Redis, etc.).
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi.middleware.cors import CORSMiddleware

from adk_celery_broker import (
    A2aTask,
    BaseA2aTaskStore,
    InMemoryA2aTaskStore,
    TaskStatus,
    get_fastapi_app,
    registry,
)


# ---------------------------------------------------------------------------
# Stub agent — replace with your real google.adk.agents.BaseAgent subclass
# ---------------------------------------------------------------------------

class MyAgent:
    async def run(self, payload: Dict[str, Any], session_service: Any = None) -> Dict[str, Any]:
        await asyncio.sleep(0.1)  # simulate work
        return {"response": "Hello from MyAgent", "echo": payload}


# ---------------------------------------------------------------------------
# Stub session service — replace with google.adk.sessions.DatabaseSessionService
# ---------------------------------------------------------------------------

class MySessionService:
    """Minimal stub; in production use ADK's DatabaseSessionService."""
    pass


# ---------------------------------------------------------------------------
# Example custom task store — replace with a real DB-backed implementation
#
# In production you might use SQLAlchemy + asyncpg, motor (MongoDB), etc.
# The only requirement is implementing BaseA2aTaskStore's four async methods.
# ---------------------------------------------------------------------------

class MyPostgresTaskStore(BaseA2aTaskStore):
    """Illustrative stub — wire up your real DB client here."""

    def __init__(self) -> None:
        # Replace with: self._pool = await asyncpg.create_pool(DSN)
        self._mem: Dict[str, A2aTask] = {}

    async def save(self, task: A2aTask) -> None:
        self._mem[task.id] = task

    async def get(self, task_id: str) -> Optional[A2aTask]:
        return self._mem.get(task_id)

    async def list_tasks(self) -> List[A2aTask]:
        return list(self._mem.values())

    async def delete(self, task_id: str) -> None:
        self._mem.pop(task_id, None)


# ---------------------------------------------------------------------------
# Wire everything together
# ---------------------------------------------------------------------------

AGENT_ID = "my_agent"

registry.register(
    AGENT_ID,
    agent_factory=MyAgent,
    session_service_factory=MySessionService,
    task_store_factory=MyPostgresTaskStore,  # workers use this
)

# The task_store instance passed here is shared across all requests in this
# process.  Workers get their own instance via task_store_factory() above.
app = get_fastapi_app(
    agent_id=AGENT_ID,
    task_store=MyPostgresTaskStore(),
    title="My Agent API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
