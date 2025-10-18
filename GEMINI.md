# Pitwall Project Overview

This document provides a comprehensive overview of the Pitwall project, a Discord bot for Formula 1 enthusiasts. It outlines the project's architecture, how to build and run it, and the development conventions to follow.

## 1. Project Overview

Pitwall is a Python-based, multi-container application that provides real-time Formula 1 race updates and on-demand data through a Discord bot. It leverages a microservices architecture to separate data acquisition from Discord notifications, using Redis as a message broker.

### Key Technologies

*   **Backend:** Python
*   **Discord Bot Framework:** discord.py
*   **Data Source:** Live timing data feed, supplemented by the FastF1 library for historical data.
*   **Message Broker:** Redis
*   **Containerization:** Docker, with `podman compose` or `docker compose` for orchestration.
*   **Machine Learning:** The `transformers` and `torch` libraries are used for team radio transcription.

### Architecture

The application is divided into two main sets of services:

*   **Publisher Services (`publisher/`):** These services connect to the live timing data feed, process the data, and publish it to specific Redis channels. Each service is responsible for a specific type of data (e.g., race control messages, timing data, pitlane information).
*   **Discord Services (`discord/`):** These services subscribe to the Redis channels. When a message is received, they format it and send it to a configured Discord webhook or respond to a slash command.

## 2. Building and Running the Project

The project is designed to be run as a set of containers orchestrated by `podman compose` or `docker compose`.

### Prerequisites

*   Docker or Podman with `podman compose` installed.
*   Git.

### Setup and Configuration

1.  **Clone the repository:**
    ```bash
    git clone https://gitlab.com/CSniper/pitwall.git
    cd pitwall
    ```

2.  **Configure environment variables:**
    *   **Publisher:** Copy the example environment file and edit it with your Redis settings if they differ from the defaults.
        ```bash
        cp publish.env.example publish.env
        ```
    *   **Discord Bot:** Copy the example environment file and add your Discord bot token and webhook URL.
        ```bash
        cp discord.env.example discord.env
        ```

### Running the Application

You can run the application in either "production" or "development" mode. The development mode includes a mock API for testing purposes.

*   **To run in production mode:**
    ```bash
    # Using podman compose
    podman compose -f compose.yaml up -d

    # Using docker compose
    docker compose -f compose.yaml up -d
    ```

*   **To run in development mode:**
    ```bash
    # Using podman compose
    podman compose -f compose.dev.yaml up -d

    # Using docker compose
    docker compose -f compose.dev.yaml up -d
    ```

### Stopping the Application

To stop the application, use the following command in the project's root directory:
```bash
# Using podman compose
podman compose -f compose.yaml down

# Using docker compose
docker compose -f compose.yaml down
```

## 3. Development Conventions

### Code Style

The project does not have a strict, documented code style. However, by examining the code, we can infer the following conventions:

*   **File Naming:** Files are named using `snake_case.py`.
*   **Variable Naming:** Variables and functions are also named using `snake_case`.
*   **Imports:** Standard library imports are listed first, followed by third-party library imports.

### Testing

There are no dedicated unit tests in the repository. Testing seems to be done manually, likely through the development environment with the mock API.

### Contribution Guidelines

The `README.md` file does not provide specific contribution guidelines. However, it does acknowledge a contributor, suggesting that contributions are welcome.

### TODO

*   **Add a formal code style guide:** To ensure consistency, a tool like Black or Flake8 could be integrated into the development process.
*   **Implement a testing framework:** Adding a testing framework like `pytest` would improve the project's reliability and make it easier to contribute to.
*   **Create a contribution guide:** A `CONTRIBUTING.md` file would make it easier for new contributors to get involved.
