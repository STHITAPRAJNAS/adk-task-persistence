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

from celery import Celery
from adk_persistence.celery.config import settings

def create_celery_app() -> Celery:
    """
    Creates and configures the Celery application using settings from config.py.
    """
    app = Celery(
        "adk_persistence.celery",
        broker=settings.redis_broker_url,
        backend=settings.redis_backend_url,
        include=["adk_persistence.celery.worker"] # Ensure worker tasks are discovered
    )

    app.conf.update(
        task_track_started=settings.celery_task_track_started,
        task_serializer=settings.celery_task_serializer,
        result_serializer=settings.celery_result_serializer,
        accept_content=settings.celery_accept_content,
        timezone=settings.celery_timezone,
        enable_utc=settings.celery_enable_utc,
        broker_connection_retry_on_startup=True,
    )

    return app

# Default singleton app instance
celery_app = create_celery_app()
