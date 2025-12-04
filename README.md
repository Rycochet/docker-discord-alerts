
# Docker Discord Notifier

Monitor your Docker containers effortlessly and receive real-time alerts in Discord with rich, customizable embeds. This project leverages Docker Compose to run the monitoring script as a continuous service, ensuring you stay informed on container events such as start, stop, restart, and failures.

## Features

- **Real-Time Monitoring**: Listens for Docker container events (`create`, `start`, `pause`, `unpause`, `restart`, `stop`, `kill`, `die`, `health_status`).
- **Discord Notifications**: Sends event alerts to a Discord channel using webhooks.
- **Rich Embeds**: Includes detailed information with fields for event type, timestamp, and shutdown reasons.
- **Configurable**: Easily customize alerts using a ENC vars.
- **Dockerized**: Run the script as a background service using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed on your system.
- A Discord account and a webhook URL from your server.

## Installation

1. **Clone the Repository**

    ```bash
    git clone https://github.com/your-username/docker-discord-monitor.git
    cd docker-discord-monitor
    ```

2. **Set Up the Configuration File**

    Example `compose.yaml` file:

    ```yaml
    services:
        docker-discord-alerts:
            container_name: docker-discord-alerts
            build: "."
            pull_policy: build
            restart: unless-stopped
            volumes:
                - "/var/run/docker.sock:/var/run/docker.sock:ro"
            environment:
                # DOCKER_HOST: "tcp://socket-proxy:2375" # socket-proxy is safer than sharing the socket as a volume!
                DISCORD_WEBHOOK_URL: "https://discord.com/api/webhooks/..." # Get this from Discord
                CONTAINERS: "*" # Default for watching everything, comma separated
                EVENTS: "default" # "all", "default" = "start,pause,unpause,stop,restart,health_status"
                EXTRA: "" # Maybe ping someone with "<@USER_ID>"
                LOG_LEVEL: "INFO" # Normal linux log levels
                VERBOSE: "False" # Gives more information on events
    ```

## Usage

1. **Build and Start the Service**

    Use Docker Compose to build and start the service in the background:

    ```bash
    docker-compose up -d
    ```

2. **Trigger Docker Events**

    Start, stop, or restart Docker containers to trigger notifications:

    ```bash
    docker start your_container_name
    docker stop your_container_name
    docker restart your_container_name
    ```

3. **Check Discord**

    Notifications will appear in the designated Discord channel with details about each container event.

## Troubleshooting

- Ensure Docker and Docker Compose are running correctly.
- Verify that the Discord webhook URL is correct and active.
- Check for any errors in the container logs:

    ```bash
    docker logs docker-discord-monitor
    ```
