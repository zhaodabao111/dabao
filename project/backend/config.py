from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Application configuration loaded from backend/.env when present."""

    app_name: str = "语音约碰面地点 API"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8003
    frontend_origin: str = "http://localhost:5175"
    public_base_url: str = "http://localhost:8003"
    recording_storage_dir: Path = BACKEND_DIR / "storage" / "recordings"
    recording_ttl_hours: int = 24
    audio_min_duration_seconds: float = 1
    audio_max_duration_seconds: float = 60
    audio_max_size_bytes: int = 5 * 1024 * 1024
    audio_probe_timeout_seconds: float = 10
    ffprobe_binary: str = "ffprobe"

    bailian_api_key: str = ""
    bailian_asr_url: str = (
        "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/"
        "compatible-mode/v1/chat/completions"
    )
    bailian_asr_model: str = "qwen3-asr-flash"
    bailian_asr_timeout_seconds: float = 30
    asr_max_base64_bytes: int = 10 * 1024 * 1024
    bailian_tts_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/"
        "aigc/multimodal-generation/generation"
    )
    bailian_tts_model: str = "qwen3-tts-flash"
    bailian_tts_voice: str = "Cherry"

    deepseek_api_key: str = ""
    deepseek_chat_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_extract_timeout_seconds: float = 30

    amap_api_key: str = ""
    amap_geocode_url: str = "https://restapi.amap.com/v3/geocode/geo"
    amap_around_url: str = "https://restapi.amap.com/v3/place/around"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
