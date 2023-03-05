from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine.base import Engine
from sqlalchemy.exc import OperationalError, ResourceClosedError
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from time import sleep
from typing import Union, Optional, Any, List
import logging
from app.common.config import TestConfig, ProdConfig, LocalConfig

Base = declarative_base()


class MySQL:
    @staticmethod
    def get_query(engine: Engine, query: str) -> Optional[Any]:
        with engine.connect() as conn:
            result = conn.execute(
                text(query + ";" if not query.endswith(";") else query)
            )
            try:
                result = result.fetchall()
            except ResourceClosedError:
                result = None
            print(f">>> Query '{query}' result:", result)
            return result

    @staticmethod
    def clear_all_table_data(engine: Engine, except_tables: Optional[List[str]] = None):
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            for table in Base.metadata.sorted_tables:
                conn.execute(table.delete()) if table.name not in except_tables else ...
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            conn.commit()

    @classmethod
    def is_db_exists(cls, engine: Engine, database_name: str) -> bool:
        return bool(
            cls.get_query(
                engine=engine,
                query=f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{database_name}';",
            )
        )

    @classmethod
    def drop_db(cls, engine: Engine, database_name: str) -> None:
        return cls.get_query(
            engine=engine,
            query=f"DROP DATABASE {database_name};",
        )

    @classmethod
    def create_db(cls, engine: Engine, database_name: str) -> None:
        return cls.get_query(
            engine=engine,
            query=f"CREATE DATABASE {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;",
        )

    @classmethod
    def create_user(
        cls,
        engine: Engine,
        username: str,
        password: str,
        host: str,
    ) -> None:
        return cls.get_query(
            engine=engine,
            query=f"CREATE USER '{username}'@'{host}' IDENTIFIED BY '{password}'",
        )

    @classmethod
    def grant_user(
        cls,
        engine: Engine,
        grant: str,
        on: str,
        to_user: str,
        user_host: str,
    ) -> None:
        return cls.get_query(
            engine=engine,
            query=f"GRANT {grant} ON {on} TO '{to_user}'@'{user_host}'",
        )


class SQLAlchemy:
    def __init__(
        self,
        app: FastAPI = None,
        config: Optional[Union[LocalConfig, ProdConfig, TestConfig]] = None,
    ):
        self.engine: Optional[Engine] = None
        self.session: Session = None
        if app is not None:
            self.init_app(app=app, config=config)

    def init_app(
        self, app: FastAPI, config: Union[LocalConfig, TestConfig, ProdConfig]
    ):
        print(">>> Current config status:", config)
        self.engine = create_engine(
            config.mysql_root_url,
            echo=config.db_echo,
            pool_recycle=config.db_pool_recycle,
            pool_pre_ping=True,
        )  # Root user
        while True:  # Connection check
            try:
                assert MySQL.is_db_exists(
                    self.engine, database_name=config.mysql_database
                ), f"Database {config.mysql_database} does not exists."
            except OperationalError:
                sleep(5)
            else:
                break

        if config.test_mode:  # Test mode
            assert isinstance(
                config, TestConfig
            ), "Config with 'test_mode == True' must be TestConfig! "
            assert (
                self.engine.url.host == "localhost"
            ), "DB host must be 'localhost' in test environment!"
            if MySQL.is_db_exists(
                self.engine, database_name=config.mysql_test_database
            ):
                MySQL.drop_db(self.engine, database_name=config.mysql_test_database)
            MySQL.create_db(self.engine, database_name=config.mysql_test_database)
            self.engine.dispose()
            self.engine = create_engine(
                config.mysql_test_url,
                echo=config.db_echo,
                pool_recycle=config.db_pool_recycle,
                pool_pre_ping=True,
            )
        else:  # Production or Local mode
            assert isinstance(
                config, Union[LocalConfig, ProdConfig]
            ), "Config with 'test_mode == False' must be LocalConfig or ProdConfig!"
            assert MySQL.is_db_exists(
                self.engine, database_name=config.mysql_database
            ), f"Database {config.mysql_database} does not exists!"
            self.engine.dispose()
            self.engine = create_engine(
                config.mysql_url,
                echo=config.db_echo,
                pool_recycle=config.db_pool_recycle,
                pool_pre_ping=True,
            )
            assert self.engine.url.username != "root", "Database user must not be root!"
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

        @app.on_event("startup")
        async def startup():
            self.engine.connect()
            logging.info("DB connected.")
            # create_task(background_task_state.run())

        @app.on_event("shutdown")
        async def shutdown():
            self.session.remove()
            self.engine.dispose()
            logging.info("DB disconnected")

    def get_db(self) -> Session:
        local_session = self.session()
        try:
            yield local_session
        finally:
            local_session.close()


db = SQLAlchemy()
