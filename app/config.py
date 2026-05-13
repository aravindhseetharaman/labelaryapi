from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='LABEL_', env_file='.env', extra='ignore')

    host: str = '0.0.0.0'
    port: int = 8081
    labelary_base_url: str = 'http://api.labelary.com/v1/printers'
    labelary_dpmm: str = '8dpmm'
    label_width_inches: int = 4
    label_height_inches: int = 2


settings = Settings()
