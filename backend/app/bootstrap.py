from app.config import settings
from app.demo_seed import seed_demo_data
from app.repositories.dependencies import sqlalchemy_uow_factory


def main() -> None:
    seed_demo_data(sqlalchemy_uow_factory, settings.sub_api_key_pepper)
    print("TAILER demo seed is ready.")


if __name__ == "__main__":
    main()
