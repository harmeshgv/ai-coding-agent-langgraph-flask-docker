---
description: Running and debugging the Coding Agent locally
---

# Local Running & Debugging Guide

This guide explains how to run or debug the Flask dashboard (`webapp`) and the LangGraph agent (`ai-coding-agent`) directly on your host machine while keeping Docker-based workbench semantics intact.

## 1. Prerequisites

1. Docker and Docker Compose installed (the workbench continues to run inside Docker).
2. Python 3.11+ with [uv](https://docs.astral.sh/uv/) installed locally.
3. `.env` populated with the same values used for the compose setup (copy `dotenv` → `.env`).
4. Workspace and instance folders created locally (`./workspace`, `./app/instance` by default).

## 2. Understand the Container/Host Split

- `docker-compose.yaml` always starts three containers: `webapp`, `ai-coding-agent`, and the workbench (e.g., `workbench-backend`).
- When you run the Python entry points locally, **stop the corresponding compose service first**. For example, to debug the Flask dashboard locally, bring down or stop the `webapp` container; to debug the LangGraph agent locally, stop `ai-coding-agent`.
- The workbench container keeps running in Docker. It must remain alive because shell commands and tests are executed there.
- The host and containers share identical directories via volumes:
  - `./workspace` ↔ `$WORKSPACE` inside both the agent and workbench containers.
  - `./app/instance` ↔ `/coding-agent/app/instance` for the SQLite database.
  This ensures that code edited or generated locally is immediately visible to the workbench.

## 3. Stopping Services Before Local Runs

```bash
docker compose stop webapp ai-coding-agent   # stop whichever service you plan to run locally
docker compose up -d workbench-backend       # ensure the workbench stays up (adjust name per stack)
```

> ⚠️ Do not leave both the containerized service and the local process running simultaneously—they will compete for the same ports (`5000` for webapp) and shared volumes.

## 4. Running the Flask Dashboard or the LangGraph Agent Locally

1. Export the same environment variables used in compose (the `.env` file is easiest):

   ```bash
   set -a
   source .env
   set +a
   ```

   Override paths to use different path than the default paths in the compose file.
   You need it, if your docker deamon runs as a different user than your local user.

   ```bash
   export WORKSPACE=/home/you/path/to/workspace
   export INSTANCE_DIR=/home/you/path/to/instance
   ```

   If you need to use another workbench container name, set the `WORKBENCH` environment variable
   and the `AGENT_STACK` environment variable (only needed for the agent):

   ```bash
   export WORKBENCH=workbench-backend-local
   export AGENT_STACK=backend
   ```

2. (Optional) If your docker deamon runs as a different user, you need to start the workbench container as a daemon with the same user as your local user:

    ```bash
    export UID
    export GID=$(id -g)
    mkdir -p .docker-home .docker-home/.m2
    docker run -d \
    --name "$WORKBENCH" \
    --user "$UID:$GID" \
    -e HOME=/home/user-home \
    -e MAVEN_CONFIG=/home/user-home/.m2 \
    -w /coding-agent-workspace \
    -v "${PWD}/.docker-home:/home/user-home" \
    -v "${PWD}/workspace-local:/coding-agent-workspace" \
    maven:3.9-eclipse-temurin-21\
    tail -f /dev/null
    ```  

    You can leave the workbench container running in docker. It is not used by the agent if you run it from the docker compose file.

    If you want to run an extra fronted workbench, you need to adjust the environment variables e.g.:

    ```bash
    export WORKBENCH=workbench-frontend-local
    export AGENT_STACK=frontend
    ```

    ... and replace the used docker image.

3. Install dependencies locally:

    ```bash
    uv sync
    ```

4. Run the Flask dashboard:

    ```bash
    uv run run_web.py
    ```

    or the LangGraph agent:

    ```bash
    uv run run_agent.py
    ```

## VS Code `launch.json`

Place the following file under `.vscode/launch.json` to reuse the same settings when launching either entry point from VS Code.
You may need to adjust `WORKBENCH`, `AGENT_STACK`, `WORKSPACE` or `INSTANCE_DIR` to match your local setup:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Run Agent",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/run_agent.py",
            "console": "integratedTerminal",
            "envFile": "${workspaceFolder}/.env",            
            "cwd": "${workspaceFolder}",
            "env": {
                "WORKSPACE": "${workspaceFolder}/workspace",
                "INSTANCE_DIR": "${workspaceFolder}/app/instance",
                "ENABLE_MCP_SERVERS": "false",
                "WORKBENCH": "workbench-backend",
            }
        },
        {
            "name": "Python: Run Web",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/run_web.py",
            "console": "integratedTerminal",
            "envFile": "${workspaceFolder}/.env",
            "cwd": "${workspaceFolder}",
            "env": {
                "WORKSPACE": "${workspaceFolder}/workspace",
                "INSTANCE_DIR": "${workspaceFolder}/app/instance",
                "ENABLE_MCP_SERVERS": "false"
            }
        }
    ]
}
```
