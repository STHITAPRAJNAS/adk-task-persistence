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

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class CeleryConfig(BaseSettings):
    """Configuration for Celery and Redis."""

    redis_broker_url: str = "redis://localhost:6379/0"
    redis_backend_url: str = "redis://localhost:6379/0"

    # Celery specific configs
    celery_task_track_started: bool = True
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list[str] = ["json"]
    celery_timezone: str = "UTC"
    celery_enable_utc: bool = True

    # Task specific configs
    max_retries: int = 3
    retry_backoff: bool = True
    retry_backoff_max: int = 600

    # Factory paths for dynamic loading in distributed worker processes
    # Example format: "my_module.factories:get_agent"
    agent_factory_path: Optional[str] = None
    session_service_factory_path: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Global config instance
settings = CeleryConfig()
