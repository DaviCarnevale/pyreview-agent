"""Application settings and configuration validation using Pydantic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """Configuration model for PyReview Agent."""

    openai_api_key: str = Field(
        default="",
        description="OpenAI API key used for code review agent completions.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model identifier (e.g. gpt-4o-mini, gpt-4o).",
    )
    openai_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for the language model.",
    )
    max_agent_iterations: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Maximum loop iterations the agent can perform per user turn.",
    )
    max_file_lines: int = Field(
        default=800,
        ge=10,
        le=5000,
        description="Maximum number of lines returned when reading a single file.",
    )
    max_file_bytes: int = Field(
        default=200_000,
        ge=1024,
        le=5_000_000,
        description="Maximum file size in bytes to read without truncation.",
    )

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def sanitize_api_key(cls, value: Optional[str]) -> str:
        """Strip whitespace and return empty string if None."""
        if value is None:
            return ""
        return str(value).strip()

    def validate_api_key(self) -> None:
        """Explicit validation to ensure the API key is present before live execution."""
        if not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is missing. Please set it in your environment or in a .env file."
            )


def get_settings(env_file: Optional[Path | str] = None) -> Settings:
    """Load environment variables and return a validated Settings instance."""
    if env_file:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        load_dotenv(override=False)

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
        max_agent_iterations=int(os.getenv("MAX_AGENT_ITERATIONS", "12")),
        max_file_lines=int(os.getenv("MAX_FILE_LINES", "800")),
        max_file_bytes=int(os.getenv("MAX_FILE_BYTES", "200000")),
    )
