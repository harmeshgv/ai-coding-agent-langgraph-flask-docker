# Testing with Environment Settings

This guide explains how to work with the centralized `EnvironmentSettings` system in tests.

## Overview

The application uses a lazy-initialized `EnvironmentSettings` dataclass to centralize all environment variable access. This design makes testing easier by allowing you to inject mock settings without modifying actual environment variables.

## Key Concepts

### Lazy Initialization

Settings are loaded only when first accessed via `get_env_settings()`, not at module import time. This allows tests to set up their environment before any code tries to read settings.

### Required vs Optional Settings

Only two settings are **required** at application startup:
- `ENCRYPTION_KEY` - For database encryption
- `WORKSPACE` - Path to the coding workspace

All other settings (including `GITHUB_TOKEN`) are **optional** and validated when used via helper methods like `require_github_token()`.

## Basic Test Setup

The test suite automatically sets up minimal environment settings via an autouse fixture in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def setup_test_env_settings():
    """Runs before each test to set up minimal settings."""
    from app.core.config import set_env_settings
    from app.core.environment_settings import EnvironmentSettings
    
    test_settings = EnvironmentSettings(
        encryption_key=os.environ["ENCRYPTION_KEY"],
        workspace=str(PROJECT_ROOT / "workspace"),
        workbench="test-workbench",
        database_dir=str(PROJECT_ROOT / "instance"),
    )
    
    set_env_settings(test_settings)
    yield
    set_env_settings(None)  # Reset after test
```

This fixture ensures every test starts with clean, minimal settings.

## Customizing Settings for Specific Tests

### Option 1: Override with Custom Settings

If your test needs specific settings (e.g., GitHub token, API keys), create custom settings:

```python
def test_github_functionality():
    """Test that requires GitHub token."""
    from app.core.config import set_env_settings
    from app.core.environment_settings import EnvironmentSettings
    
    # Create settings with GitHub token
    test_settings = EnvironmentSettings(
        encryption_key="test-key-32-bytes-long-exactly!!",
        workspace="/tmp/test-workspace",
        github_token="test-github-token-12345",
    )
    
    set_env_settings(test_settings)
    
    # Your test code here
    # ...
```

### Option 2: Use Environment Variables

For integration tests, you can set environment variables before importing:

```python
import os

def test_with_real_env():
    """Test using actual environment variables."""
    os.environ["GITHUB_TOKEN"] = "real-token-from-ci"
    
    # Reset settings to force reload from environment
    from app.core.config import set_env_settings
    set_env_settings(None)
    
    # Now get_env_settings() will read from environment
    from app.core.config import get_env_settings
    settings = get_env_settings()
    
    assert settings.github_token == "real-token-from-ci"
```

## Testing Without Optional Settings

Tests that don't need certain features can run without their settings:

```python
def test_non_github_feature():
    """Test that doesn't use GitHub - no token needed."""
    from app.core.config import get_env_settings
    
    # This works fine without github_token
    settings = get_env_settings()
    assert settings.workspace is not None
    
    # If code tries to use GitHub, it will fail with clear error
    # settings.require_github_token()  # Would raise ValueError
```

## Validation Helpers

Use validation helpers when your code requires specific settings:

```python
def my_github_function():
    """Function that needs GitHub access."""
    from app.core.config import get_env_settings
    
    settings = get_env_settings()
    
    # This raises ValueError with helpful message if token not set
    token = settings.require_github_token()
    
    # Use token...
```

Available validation helpers:
- `require_github_token()` - Validates GitHub token is set
- `require_encryption_key()` - Validates encryption key is set
- `require_llm_api_key(provider)` - Validates LLM API key for specific provider

## Testing Validation Errors

Test that your code properly validates required settings:

```python
def test_github_function_requires_token():
    """Test that function fails gracefully without token."""
    from app.core.config import set_env_settings
    from app.core.environment_settings import EnvironmentSettings
    import pytest
    
    # Create settings WITHOUT github_token
    test_settings = EnvironmentSettings(
        encryption_key="test-key-32-bytes-long-exactly!!",
        workspace="/tmp/test-workspace",
    )
    
    set_env_settings(test_settings)
    
    # Test that function raises appropriate error
    with pytest.raises(ValueError, match="GITHUB_TOKEN is required"):
        my_github_function()
```

## Common Patterns

### Testing with Multiple LLM Providers

```python
@pytest.mark.parametrize("provider,api_key", [
    ("openai", "sk-test-openai-key"),
    ("mistral", "test-mistral-key"),
    ("anthropic", "sk-ant-test-key"),
])
def test_llm_provider(provider, api_key):
    """Test different LLM providers."""
    from app.core.config import set_env_settings
    from app.core.environment_settings import EnvironmentSettings
    
    settings = EnvironmentSettings(
        encryption_key="test-key-32-bytes-long-exactly!!",
        workspace="/tmp/test-workspace",
        **{f"{provider}_api_key": api_key}
    )
    
    set_env_settings(settings)
    
    # Test provider-specific functionality
    # ...
```

### Testing Configuration Fallbacks

```python
def test_database_uri_fallback():
    """Test that database URI falls back to default."""
    from app.core.config import get_env_settings
    from pathlib import Path
    
    settings = get_env_settings()
    
    # Without database_url, should use default sqlite path
    base_dir = Path("/tmp/test")
    uri = settings.get_database_uri(base_dir)
    
    assert "sqlite:///" in uri
    assert "instance/agent.db" in uri
```

## Best Practices

1. **Keep tests isolated**: Always use the autouse fixture to reset settings between tests
2. **Test validation**: Verify your code properly validates required settings
3. **Minimal settings**: Only set the settings your test actually needs
4. **Clear errors**: Use validation helpers to provide helpful error messages
5. **Mock external services**: Don't make real API calls in unit tests even with valid tokens

## Troubleshooting

### "ENCRYPTION_KEY is not set" Error

Make sure `tests/conftest.py` is being loaded. It sets up required environment variables.

### Settings Not Resetting Between Tests

The autouse fixture should handle this automatically. If you're seeing state bleed between tests, check that you're not caching `get_env_settings()` results globally.

### Import Errors During Test Collection

If tests fail during collection (before any test runs), it means some module is trying to access settings at import time. This shouldn't happen with lazy initialization - report it as a bug.

## Example: Complete Test File

```python
"""Example test file showing environment settings patterns."""

import pytest
from app.core.config import get_env_settings, set_env_settings
from app.core.environment_settings import EnvironmentSettings


def test_basic_functionality():
    """Test that doesn't need special settings."""
    settings = get_env_settings()
    assert settings.workspace is not None


def test_with_github_token():
    """Test that needs GitHub access."""
    # Override settings for this test
    test_settings = EnvironmentSettings(
        encryption_key="test-key-32-bytes-long-exactly!!",
        workspace="/tmp/test",
        github_token="test-token-12345",
    )
    set_env_settings(test_settings)
    
    settings = get_env_settings()
    token = settings.require_github_token()
    assert token == "test-token-12345"


def test_missing_token_raises_error():
    """Test validation error for missing token."""
    settings = get_env_settings()
    
    with pytest.raises(ValueError, match="GITHUB_TOKEN is required"):
        settings.require_github_token()
```

## Migration from Old Tests

If you have old tests that set environment variables directly:

**Before:**
```python
import os

def test_old_style():
    os.environ["GITHUB_TOKEN"] = "test-token"
    # Test code...
```

**After:**
```python
from app.core.config import set_env_settings
from app.core.environment_settings import EnvironmentSettings

def test_new_style():
    test_settings = EnvironmentSettings(
        encryption_key="test-key-32-bytes-long-exactly!!",
        workspace="/tmp/test",
        github_token="test-token",
    )
    set_env_settings(test_settings)
    # Test code...
```

The new style is preferred because:
- More explicit and type-safe
- Doesn't pollute global environment
- Automatically reset by fixture
- Works consistently across all tests
