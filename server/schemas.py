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
