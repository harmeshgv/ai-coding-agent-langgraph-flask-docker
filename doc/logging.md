# Logging

This document describes the logging setup, configuration options, and extension points for the application.

## Overview

Logging is initialized once at startup via `setup_logging()` in `app/core/utils.py`. Both entrypoints call it before any other application code runs:

- `run_agent.py` – agent worker process
- `run_web.py` – Flask web server

The function returns the `entrypoint` logger, which is used for startup messages. All other modules obtain their own logger via `logging.getLogger(__name__)`.

## Default Configuration

When no external configuration file is supplied, the built-in dictConfig is used:

| Component             | Setting                                        |
|-----------------------|------------------------------------------------|
| Root level            | `DEBUG` (all messages flow to handlers)        |
| Console handler level | `INFO` (only INFO and above printed to stdout) |
| Format                | `%(name)s - %(levelname)s - %(message)s`       |

### Noisy third-party loggers

The following loggers are pinned to `WARNING` to suppress verbose output:

- `httpx`
- `httpcore`
- `werkzeug`

## External Configuration File

An external file overrides the built-in defaults entirely. Supply it in one of two ways:

1. **Environment variable** – set `LOGGING_CONFIG_FILE` to the file path before starting the process.
2. **Code** – pass `config_file=Path("path/to/file")` directly to `setup_logging()`.

If the file path is provided but the file cannot be found, a warning is emitted and the built-in defaults remain in effect. This helps catch typos and missing local overrides early during startup.

### Supported formats

| Extension                    | Loader                          |
|------------------------------|---------------------------------|
| `.json`                      | `logging.config.dictConfig`     |
| `.ini`, `.cfg`, or any other | `logging.config.fileConfig`     |

The file is detected by its suffix (case-insensitive). If the path does not exist the built-in default is used as a fallback.

### JSON format

The JSON file must follow the standard Python logging dict-config schema. A ready-to-use example with a rotating file handler is provided at `logging.json` in the project root:

```json
{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": {
    "standard": {
      "format": "%(asctime)s %(name)s - %(levelname)s - %(message)s",
      "datefmt": "%Y-%m-%d %H:%M:%S"
    }
  },
  "handlers": {
    "console": {
      "class": "logging.StreamHandler",
      "level": "INFO",
      "formatter": "standard"
    },
    "rolling_file": {
      "class": "logging.handlers.RotatingFileHandler",
      "level": "DEBUG",
      "formatter": "standard",
      "filename": "logs/agent-debug.log",
      "maxBytes": 5000000,
      "backupCount": 5
    }
  },
  "root": {
    "level": "DEBUG",
    "handlers": ["console", "rolling_file"]
  },
  "loggers": {
    "httpx": { "level": "WARNING" },
    "httpcore": { "level": "WARNING" },
    "werkzeug": { "level": "WARNING" }
  }
}
```

> **Note:** `setup_logging()` now ensures the parent directories for `filename` targets exist before the handlers are instantiated. Any creation failure is reported with a warning so you can fix permissions or choose a different path.
>
> The loader also defaults `"disable_existing_loggers"` to `false` if the key is omitted to avoid accidentally shutting off third-party loggers that were configured earlier in the import chain.

### INI format

The INI file must follow the `logging.config.fileConfig` schema (sections `[loggers]`, `[handlers]`, `[formatters]`). See the [Python docs](https://docs.python.org/3/library/logging.config.html#configuration-file-format) for the full specification.

### Running in Docker

When the stack runs under Docker (via `docker-compose up`), set the env var in `.env` so every service receives the custom configuration automatically:

```dotenv
LOGGING_CONFIG_FILE=logging.json
```

The compose file already mounts the project root, so `logging.json` is available inside the container at the same relative path. Adjust the value if you store the file elsewhere (e.g., `.local/logging.json`). Remember to restart the containers after changing `.env` so the new variable propagates.

#### Tail the rotating log file inside the container

The sample JSON config writes DEBUG output to `logs/agent-debug.log`. To inspect it while the container is running:

```bash
docker exec -it ai-coding-agent tail -f logs/agent-debug.log
```

Replace `ai-coding-agent` with the container name reported by `docker ps` if you use a different service name. The `tail -f` command follows rotations performed by the `RotatingFileHandler`, so you can watch live log output without leaving the container.

## Adding a Rolling File Handler

To capture DEBUG output to a rotating log file, use the JSON config above (or the `.local/logging.json` local override) and point `LOGGING_CONFIG_FILE` at it:

```bash
export LOGGING_CONFIG_FILE=logging.json
python run_agent.py
```

The file rotates at 5 MB and keeps 5 backups by default. Adjust `maxBytes` and `backupCount` in the config file as needed.

## Adding a Module-Specific Logger

To set a different level or handler set for a specific module, add an entry under `loggers` in the JSON config:

```json
"app.agent.nodes.coder": {
  "level": "DEBUG",
  "handlers": ["console"],
  "propagate": false
}
```

Setting `propagate` to `false` prevents the message from also being handled by the root logger (and therefore the rolling file handler).

## Activating DEBUG on the Console

The console handler is fixed at `INFO` in both the built-in default and the example `logging.json`. To see DEBUG messages on the console, change the console handler level:

```json
"console": {
  "class": "logging.StreamHandler",
  "level": "DEBUG",
  "formatter": "standard"
}
```

## Timestamp Format

To include date and time in log lines, add `%(asctime)s` to the formatter and optionally set `datefmt`:

```json
"standard": {
  "format": "%(asctime)s %(name)s - %(levelname)s - %(message)s",
  "datefmt": "%Y-%m-%d %H:%M:%S"
}
```

For millisecond precision use `"%Y-%m-%d %H:%M:%S.%f"`.

## See Also

- [Environment Settings](./environment_settings.md) – all environment variables including `LOGGING_CONFIG_FILE`
- [Python logging.config docs](https://docs.python.org/3/library/logging.config.html)
