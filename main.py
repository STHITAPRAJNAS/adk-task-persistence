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

import asyncio
from typing import Any, Dict

# Mocking Google ADK components
class BaseAgent:
    async def run(self, payload: Dict[str, Any], state: Any = None) -> Dict[str, Any]:
        print(f"Agent processing payload: {payload}")
        await asyncio.sleep(1) # Simulate work
        return {"response": "Mock agent response", "input_payload": payload}

class DatabaseSessionService:
    def __init__(self):
        self.db = {}

    async def create_task(self, task_id: str, payload: Dict[str, Any], status: str):
        self.db[task_id] = {"payload": payload, "status": status}
        print(f"DB: Created task {task_id} with status {status}")

    async def update_task_status(self, task_id: str, status: str, error: str = None, traceback: str = None):
        if task_id not in self.db:
             self.db[task_id] = {}
        self.db[task_id]["status"] = status
        print(f"DB: Updated task {task_id} to status {status}")

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        return self.db.get(task_id)

    async def load_state(self, task_id: str) -> Any:
        return self.db.get(task_id, {}).get("state")

    async def save_state_and_status(self, task_id: str, state: Any, status: str):
         if task_id not in self.db:
              self.db[task_id] = {}
         self.db[task_id]["state"] = state
         self.db[task_id]["status"] = status
         print(f"DB: Saved state for task {task_id} and updated status to {status}")

# Factories required for distributed Celery execution
def agent_factory() -> BaseAgent:
    return BaseAgent()

def session_service_factory() -> DatabaseSessionService:
    return DatabaseSessionService()

# Import the new adk_celery_broker components
from adk_celery_broker.registry import registry
from adk_celery_broker.executor import get_celery_fastapi_app

# 1. Register them under a unique ID so distributed workers know how to build them
AGENT_ID = "my_demo_agent"
registry.register(AGENT_ID, agent_factory, session_service_factory)

# 2. Build the FastAPI app using the registered agent ID
app = get_celery_fastapi_app(agent_id=AGENT_ID)

if __name__ == "__main__":
    import uvicorn
    print("Starting Uvicorn server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
