from __future__ import annotations

import os
import uuid

import pytest
from pydantic import SecretStr

from empirical_platform.shared.bootstrap import (
    RuntimeLifecycleState,
    initialize_infrastructure_runtime,
)
from empirical_platform.shared.config.settings import (
    ObjectStorageConfigSnapshot,
    PostgreSQLConfigSnapshot,
)
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState, ProcessHealth
from empirical_platform.shared.object_storage.s3 import S3ObjectStorageService
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return (
        os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"
        and os.environ.get("EMPIRICAL_PLATFORM_RUN_OBJECT_STORAGE_TESTS") == "1"
    )


def _postgres_config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-runtime-test",
    )


def _object_storage_config(
    *,
    bucket: str,
    access_key: str | None = None,
    secret_key: str | None = None,
) -> ObjectStorageConfigSnapshot:
    return ObjectStorageConfigSnapshot(
        endpoint_url=os.environ.get(
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"
        ),
        region=os.environ.get("EMPIRICAL_PLATFORM_OBJECT_STORAGE_REGION", "us-east-1"),
        foundation_bucket=bucket,
        access_key=SecretStr(
            access_key or os.environ["EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY"]
        ),
        secret_key=SecretStr(
            secret_key or os.environ["EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY"]
        ),
        secure=False,
        path_style=True,
        connection_timeout_seconds=5,
        operation_timeout_seconds=5,
        create_bucket_if_missing=True,
    )


def _runtime_env() -> dict[str, str]:
    return {
        "EMPIRICAL_PLATFORM_ENVIRONMENT": "test",
        "EMPIRICAL_PLATFORM_POSTGRES_PASSWORD": os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"],
        "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY": os.environ[
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY"
        ],
        "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY": os.environ[
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY"
        ],
    }


def test_unified_runtime_composes_postgres_and_minio_without_domain_artifacts() -> None:
    if not _integration_enabled():
        pytest.skip("Unified runtime integration requires PostgreSQL and object-storage opt-in")
    bucket = f"foundation-m010-{uuid.uuid4().hex}"
    key = f"generic-{uuid.uuid4().hex}"
    persistence = PostgresPersistenceService(_postgres_config())
    object_storage = S3ObjectStorageService(_object_storage_config(bucket=bucket))
    runtime = initialize_infrastructure_runtime(
        _runtime_env(),
        persistence=persistence,
        object_storage=object_storage,
    )
    try:
        assert runtime.lifecycle_state is RuntimeLifecycleState.READY
        assert runtime.health.status is ProcessHealth.PASS
        assert runtime.persistence is persistence
        assert runtime.object_storage is object_storage
        assert persistence.health().dependency_health is HealthState.PASS
        assert object_storage.health().dependency_health is HealthState.PASS

        with persistence.unit_of_work() as work:
            assert work.execute("SELECT 1 AS value") == [{"value": 1}]

        metadata = object_storage.put_object(key=key, payload=b"runtime", content_type="text/plain")
        assert metadata.key == key
        stored = object_storage.get_object(key)
        assert stored is not None
        assert stored.payload == b"runtime"
        assert object_storage.delete_object(key)
        object_storage.client.delete_bucket(Bucket=bucket)
    finally:
        runtime.close()
        runtime.close()

    assert runtime.lifecycle_state.value == RuntimeLifecycleState.STOPPED.value
    assert not persistence.check()
    assert not object_storage.check()


def test_unified_runtime_closes_postgres_when_minio_credentials_fail() -> None:
    if not _integration_enabled():
        pytest.skip("Unified runtime integration requires PostgreSQL and object-storage opt-in")
    persistence = PostgresPersistenceService(_postgres_config())
    object_storage = S3ObjectStorageService(
        _object_storage_config(
            bucket=f"foundation-m010-{uuid.uuid4().hex}",
            access_key="-".join(("invalid", "local", "user")),
            secret_key="-".join(("invalid", "local", "value")),
        )
    )

    with pytest.raises(FoundationError) as exc_info:
        initialize_infrastructure_runtime(
            _runtime_env(),
            persistence=persistence,
            object_storage=object_storage,
        )

    assert exc_info.value.layer == "object_storage"
    assert not persistence.check()
    assert "invalid-local-value" not in str(exc_info.value.as_dict())
