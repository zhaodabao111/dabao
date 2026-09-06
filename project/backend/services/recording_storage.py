import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


RECORDING_ID_PATTERN = re.compile(r"^rec_[0-9a-f]{32}$")


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class RecordingMetadata:
    audio_id: str
    created_at: str
    file_name: str
    size_bytes: int
    duration_seconds: float
    container: str
    codec: str
    mime_type: str

    def is_expired(
        self,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> bool:
        created_at = datetime.fromisoformat(self.created_at)
        if created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        current_time = now or datetime.now(timezone.utc)
        return current_time >= created_at + ttl


class RecordingStorage:
    def __init__(self, root: Path, *, ttl_hours: int = 24) -> None:
        self.root = root.resolve()
        self.ttl = timedelta(hours=ttl_hours)
        self.root.mkdir(parents=True, exist_ok=True)

    def create_temporary_path(self) -> Path:
        return self.root / f".upload_{uuid4().hex}.part"

    def save_recording(
        self,
        *,
        temporary_path: Path,
        size_bytes: int,
        duration_seconds: float,
        container: str,
        codec: str,
    ) -> RecordingMetadata:
        audio_id = f"rec_{uuid4().hex}"
        file_name = f"{audio_id}.webm"
        audio_path = self.root / file_name
        metadata_path = self.root / f"{audio_id}.json"
        temporary_metadata_path = self.root / f".{audio_id}.json.part"
        metadata = RecordingMetadata(
            audio_id=audio_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            file_name=file_name,
            size_bytes=size_bytes,
            duration_seconds=round(duration_seconds, 6),
            container=container,
            codec=codec,
            mime_type="audio/webm;codecs=opus",
        )

        try:
            temporary_path.replace(audio_path)
            with temporary_metadata_path.open("x", encoding="utf-8") as output:
                json.dump(asdict(metadata), output, ensure_ascii=False, indent=2)
            temporary_metadata_path.replace(metadata_path)
        except OSError as error:
            audio_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            temporary_metadata_path.unlink(missing_ok=True)
            raise StorageError from error
        return metadata

    def load_metadata(self, audio_id: str) -> RecordingMetadata | None:
        """Load metadata safely for future endpoints and enforce the 24-hour TTL."""
        if not RECORDING_ID_PATTERN.fullmatch(audio_id):
            return None
        metadata_path = self.root / f"{audio_id}.json"
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = RecordingMetadata(**payload)
            if (
                metadata.audio_id != audio_id
                or metadata.file_name != f"{audio_id}.webm"
                or metadata.is_expired(self.ttl)
            ):
                return None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        audio_path = self.root / metadata.file_name
        if (
            audio_path.parent != self.root
            or audio_path.is_symlink()
            or not audio_path.is_file()
        ):
            return None
        return metadata

    def load_audio(
        self,
        audio_id: str,
    ) -> tuple[RecordingMetadata, bytes] | None:
        """Read an unexpired recording after validating its metadata and size."""
        metadata = self.load_metadata(audio_id)
        if metadata is None:
            return None

        audio_path = self.root / metadata.file_name
        try:
            if audio_path.stat().st_size != metadata.size_bytes:
                return None
            audio_bytes = audio_path.read_bytes()
        except OSError:
            return None
        if len(audio_bytes) != metadata.size_bytes:
            return None
        return metadata, audio_bytes
