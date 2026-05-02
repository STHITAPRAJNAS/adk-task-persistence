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

from typing import Callable, Any, Dict, Tuple

class AgentRegistry:
    """
    Singleton registry to map string IDs to Agent and SessionService factory functions.
    This solves the problem of Celery workers needing to know which agent to instantiate
    when pulling a generic A2A task from Redis across distributed processes.
    """
    _registry: Dict[str, Tuple[Callable[..., Any], Callable[..., Any]]] = {}

    @classmethod
    def register(cls, agent_id: str, agent_factory: Callable[..., Any], session_service_factory: Callable[..., Any]) -> None:
        """
        Registers an agent factory and its corresponding session service factory under an ID.

        Args:
            agent_id: The unique string identifier for the agent configuration.
            agent_factory: A callable that returns the ADK Agent instance.
            session_service_factory: A callable that returns the ADK SessionService instance.
        """
        cls._registry[agent_id] = (agent_factory, session_service_factory)

    @classmethod
    def get(cls, agent_id: str) -> Tuple[Callable[..., Any], Callable[..., Any]]:
        """
        Retrieves the factories for a given agent_id.
        """
        if agent_id not in cls._registry:
            raise KeyError(f"Agent ID '{agent_id}' not found in AgentRegistry. "
                           "Ensure it is registered before tasks are executed.")
        return cls._registry[agent_id]

# Singleton instance access
registry = AgentRegistry()
