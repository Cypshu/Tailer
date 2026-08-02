from fastapi import Depends

from app.config import settings
from app.database import SessionLocal
from app.demo_seed import build_demo_records
from app.repositories.base import UnitOfWorkFactory
from app.repositories.memory import MemoryStore, MemoryUnitOfWorkFactory
from app.repositories.sqlalchemy import SqlAlchemyUnitOfWorkFactory


_users, _projects, _keys, _usage = build_demo_records(settings.sub_api_key_pepper)
memory_store = MemoryStore(
    users=_users,
    projects=_projects,
    keys=_keys,
    usage=_usage,
)
memory_uow_factory = MemoryUnitOfWorkFactory(memory_store)
sqlalchemy_uow_factory = SqlAlchemyUnitOfWorkFactory(SessionLocal)


def get_uow_factory() -> UnitOfWorkFactory:
    if settings.repository_backend == "memory":
        return memory_uow_factory
    return sqlalchemy_uow_factory


def get_service(factory: UnitOfWorkFactory = Depends(get_uow_factory)):
    from app.services import TailerService

    return TailerService(factory)
