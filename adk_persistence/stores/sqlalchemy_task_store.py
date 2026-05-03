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
SqlAlchemyTaskStore — persistent A2A task store for Google ADK.

Implements the ``a2a.server.tasks.TaskStore`` ABC so it can be passed
directly to ADK's A2A machinery:

* **Today** (before ADK PRs #3839/#4970 merge): use ``create_a2a_app()``
  from ``adk_persistence.app`` which builds the A2A stack manually.

* **After PR #4970 merges**::

    from google.adk.cli.fast_api import get_fast_api_app
    app = get_fast_api_app(
        agents_dir="./agents",
        a2a=True,
        a2a_task_store=SqlAlchemyTaskStore(engine),
    )

Tasks are serialised as JSON so the schema is forward-compatible with any
future changes to ``a2a.types.Task`` without needing migrations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine

if TYPE_CHECKING:
    from a2a.server.context import ServerCallContext
    from a2a.types import ListTasksRequest, ListTasksResponse, Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABC base — resolved at import time so SqlAlchemyTaskStore is a proper
# subclass when a2a-sdk is available, and falls back to object otherwise.
# ---------------------------------------------------------------------------
try:
    from a2a.server.tasks import TaskStore as _TaskStoreBase  # type: ignore[import]
except ImportError:  # a2a-sdk not installed (e.g. running tests without ADK)
    _TaskStoreBase = object  # type: ignore[assignment,misc]


class SqlAlchemyTaskStore(_TaskStoreBase):  # type: ignore[misc]
    """
    Async SQLAlchemy-backed ``TaskStore`` for ADK's A2A layer.

    Works with PostgreSQL, MySQL, and SQLite.  Tasks are stored as JSON so
    the schema is a single table with no ADK-version-specific columns.

    Schema (auto-created unless ``create_table=False``)::

        CREATE TABLE adk_a2a_tasks (
            id         VARCHAR(255) PRIMARY KEY,
            data       TEXT NOT NULL,        -- JSON-serialised a2a.types.Task
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );

    Usage::

        from sqlalchemy.ext.asyncio import create_async_engine
        from adk_persistence import SqlAlchemyTaskStore

        engine = create_async_engine("postgresql+asyncpg://user:pass@host/db")
        store  = SqlAlchemyTaskStore(engine)

        # Pass to ADK (after PR #4970 merges):
        app = get_fast_api_app(..., a2a=True, a2a_task_store=store)

        # Or use today via create_a2a_app():
        from adk_persistence import create_a2a_app
        app = create_a2a_app(runner=runner, agent_card=card, task_store=store)
    """

    def __init__(
        self,
        engine: AsyncEngine,
        table_name: str = "adk_a2a_tasks",
        create_table: bool = True,
    ) -> None:
        """
        Args:
            engine: An async SQLAlchemy engine.  Create one with
                ``create_async_engine("postgresql+asyncpg://...")``.
            table_name: Name of the tasks table.  Override if you need
                multiple stores in the same database.
            create_table: When ``True`` (default) the table is created on
                first use if it does not already exist.
        """
        self._engine = engine
        self._table_name = table_name
        self._create_table = create_table
        self._table: Optional[Table] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_table(self) -> Table:
        """Return the SQLAlchemy Table, creating it in the DB if needed."""
        if self._table is not None:
            return self._table

        metadata = MetaData()
        table = Table(
            self._table_name,
            metadata,
            Column("id", String(255), primary_key=True),
            Column("data", Text, nullable=False),
            Column(
                "updated_at",
                DateTime(timezone=True),
                server_default=func.now(),
            ),
        )

        if self._create_table:
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all, checkfirst=True)
            logger.debug("Ensured table '%s' exists", self._table_name)

        self._table = table
        return table

    # ------------------------------------------------------------------
    # TaskStore ABC implementation
    # ------------------------------------------------------------------

    async def save(self, task: "Task", context: "ServerCallContext") -> None:
        """Upsert a task.  Creates a new row or overwrites the existing one."""
        table = await self._ensure_table()
        data = task.model_dump_json()

        async with self._engine.begin() as conn:
            # Try UPDATE first; if no row matched, INSERT.
            # This pattern works across all supported databases without
            # needing dialect-specific ON CONFLICT clauses.
            result = await conn.execute(
                update(table).where(table.c.id == task.id).values(data=data)
            )
            if result.rowcount == 0:
                await conn.execute(
                    table.insert().values(id=task.id, data=data)
                )

    async def get(
        self, task_id: str, context: "ServerCallContext"
    ) -> Optional["Task"]:
        """Return a task by ID, or ``None`` if not found."""
        from a2a.types import Task  # type: ignore[import]

        table = await self._ensure_table()
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(table.c.data).where(table.c.id == task_id)
            )
            row = result.fetchone()

        if row is None:
            return None
        return Task.model_validate_json(row[0])

    async def list(
        self, params: "ListTasksRequest", context: "ServerCallContext"
    ) -> "ListTasksResponse":
        """Return all tasks. Respects ``params.task_ids`` filter if provided."""
        from a2a.types import ListTasksResponse, Task  # type: ignore[import]

        table = await self._ensure_table()
        stmt = select(table.c.data)

        # Honour optional task_ids filter from the A2A list request
        task_ids: list[str] = getattr(params, "task_ids", None) or []
        if task_ids:
            stmt = stmt.where(table.c.id.in_(task_ids))

        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            rows = result.fetchall()

        tasks = [Task.model_validate_json(row[0]) for row in rows]
        return ListTasksResponse(tasks=tasks)

    async def delete(self, task_id: str, context: "ServerCallContext") -> None:
        """Delete a task.  No-op if the task does not exist."""
        table = await self._ensure_table()
        async with self._engine.begin() as conn:
            await conn.execute(delete(table).where(table.c.id == task_id))
