from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root(module_path: Path) -> Path:
    source_root = module_path.resolve().parents[2]
    return source_root if (source_root / "pyproject.toml").is_file() else Path.cwd()


PROJECT_ROOT = project_root(Path(__file__))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="ADRYN_", extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str | None = Field(default=None, repr=False)
    random_seed: int = 20261001
    raw_data_dir: Path = Field(default=Path("data/raw"))
    processed_data_dir: Path = Field(default=Path("data/processed"))
    output_dir: Path = Field(default=Path("outputs"))

    def ensure_dirs(self) -> None:
        for field_name in ("raw_data_dir", "processed_data_dir", "output_dir"):
            directory = getattr(self, field_name)
            if not directory.is_absolute():
                setattr(self, field_name, PROJECT_ROOT / directory)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
