from pydantic import BaseModel
from enum import Enum

class TargetVersion(str, Enum):
    ACAD9 = "ACAD9"
    ACAD10 = "ACAD10"
    ACAD12 = "ACAD12"
    ACAD14 = "ACAD14"
    ACAD2000 = "ACAD2000"
    ACAD2004 = "ACAD2004"
    ACAD2007 = "ACAD2007"
    ACAD2010 = "ACAD2010"
    ACAD2013 = "ACAD2013"
    ACAD2018 = "ACAD2018"

class ConvertResponse(BaseModel):
    status: str
    message: str
    file_path: str | None = None

class MediaInfoResponse(BaseModel):
    format: dict
    streams: list[dict]

class VideoFormat(str, Enum):
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    AVI = "avi"
    FLV = "flv"
    WEBM = "webm"
    MP3 = "mp3"
    AAC = "aac"
    WAV = "wav"

class CompressLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class GifFormat(str, Enum):
    GIF = "gif"
    WEBP = "webp"
    JPG = "jpg"

class VideoEditParams(BaseModel):
    trim_start: str = "0"
    trim_end: str = ""
    crop: str = ""
    remove_audio: bool = False
    speed: float = 1.0
