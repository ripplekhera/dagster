import sys
from contextlib import contextmanager

import pytest

from dagster import lambda_solid, pipeline, repository
from dagster._api.snapshot_repository import sync_get_streaming_external_repositories_data_grpc
from dagster.core.errors import DagsterUserCodeProcessError
from dagster.core.host_representation import (
    ExternalRepositoryData,
    ManagedGrpcPythonEnvRepositoryLocationOrigin,
)
from dagster.core.test_utils import instance_for_test
from dagster.core.types.loadable_target_origin import LoadableTargetOrigin

from .utils import get_bar_repo_repository_location


def test_streaming_external_repositories_api_grpc(instance):
    with get_bar_repo_repository_location(instance) as repository_location:
        external_repo_datas = sync_get_streaming_external_repositories_data_grpc(
            repository_location.client, repository_location
        )

        assert len(external_repo_datas) == 1

        external_repository_data = external_repo_datas["bar_repo"]

        assert isinstance(external_repository_data, ExternalRepositoryData)
        assert external_repository_data.name == "bar_repo"


def test_streaming_external_repositories_error(instance):
    with get_bar_repo_repository_location(instance) as repository_location:
        repository_location.repository_names = {"does_not_exist"}
        assert repository_location.repository_names == {"does_not_exist"}

        with pytest.raises(
            DagsterUserCodeProcessError, match='Could not find a repository called "does_not_exist"'
        ):
            sync_get_streaming_external_repositories_data_grpc(
                repository_location.client, repository_location
            )


@lambda_solid
def do_something():
    return 1


@pipeline
def giant_pipeline():
    # Pipeline big enough to be larger than the max size limit for a gRPC message in its
    # external repository
    for _i in range(20000):
        do_something()


@repository
def giant_repo():
    return {
        "pipelines": {
            "giant": giant_pipeline,
        },
    }


@contextmanager
def get_giant_repo_grpc_repository_location(instance):
    with ManagedGrpcPythonEnvRepositoryLocationOrigin(
        loadable_target_origin=LoadableTargetOrigin(
            executable_path=sys.executable,
            attribute="giant_repo",
            module_name="dagster_tests.api_tests.test_api_snapshot_repository",
        ),
        location_name="giant_repo_location",
    ).create_single_location(instance) as location:
        yield location


@pytest.mark.skip("https://github.com/dagster-io/dagster/issues/6940")
def test_giant_external_repository_streaming_grpc():
    with instance_for_test() as instance:
        with get_giant_repo_grpc_repository_location(instance) as repository_location:
            # Using streaming allows the giant repo to load
            external_repos_data = sync_get_streaming_external_repositories_data_grpc(
                repository_location.client, repository_location
            )

            assert len(external_repos_data) == 1

            external_repository_data = external_repos_data["giant_repo"]

            assert isinstance(external_repository_data, ExternalRepositoryData)
            assert external_repository_data.name == "giant_repo"
