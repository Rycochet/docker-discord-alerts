# docker-discord-alerts

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/Rycochet/docker-discord-alerts/publish.yml)](https://github.com/Rycochet/docker-discord-alerts/actions/workflows/publish.yml) ![GitHub contributors](https://img.shields.io/github/contributors/Rycochet/docker-discord-alerts) [![Docker Pulls](https://img.shields.io/docker/pulls/rycochet/docker-discord-alerts) ![Docker Image Size](https://img.shields.io/docker/image-size/rycochet/docker-discord-alerts)](https://hub.docker.com/r/rycochet/docker-discord-alerts/)

Monitor your Docker containers effortlessly and receive real-time alerts in Discord. This project leverages Docker Compose to run the monitoring script as a continuous service, ensuring you stay informed on container events such as start, stop, restart, and failures.

![alert-verbose](https://github.com/user-attachments/assets/bc8bf763-08f2-4c85-b72a-7a5f2d7fdbba)
![alert](https://github.com/user-attachments/assets/e0d0f485-670a-45e7-8107-ab2aa7292c98)
    
## Features

- **Real-Time Monitoring**: Listens for Docker container events.
- **Discord Notifications**: Sends event alerts to a Discord channel using webhooks (no bot required).
- **Rich Embeds**: Optional detailed information.
- **Configurable**: Easily customize alerts using a ENV vars.
- **Dockerized**: Run the script as a background service using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed on your system.
- A Discord account and a webhook URL from your server.

## Usage

1. **Create a `compose.yaml` file**

    An example [compose.yaml](compose.yaml) file is included, make sure you replace the `DISCORD_WEBHOOK_URL` value with one you [obtained from Discord](https://discordjs.guide/legacy/popular-topics/webhooks):

    ```yaml
    services:
        docker-discord-alerts:
            container_name: docker-discord-alerts
            image: ghcr.io/rycochet/docker-discord-alerts:latest
            restart: unless-stopped
            volumes:
                - "/var/run/docker.sock:/var/run/docker.sock:ro" # or use the `DOCKER_HOST` variable
            environment:
                DISCORD_WEBHOOK_URL: "https://discord.com/api/webhooks/..."
    ```

1. **Start the Service**

    Use Docker Compose to start the service in the background:

    ```bash
    docker-compose up -d
    ```

1. **Trigger Docker Events**

    Start, stop, or restart Docker containers to trigger notifications:

    ```bash
    docker start your_container_name
    docker stop your_container_name
    docker restart your_container_name
    ```

1. **Check Discord**

    Notifications will appear in the designated Discord channel with details about each container event.

### Troubleshooting

- Ensure Docker and Docker Compose are running correctly.
- Verify that the Discord webhook URL is correct and active.
- Check for any errors in the container logs:

    ```bash
    docker logs docker-discord-alerts
    ```

## Environment Variables

| Name | Definition | Default |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | **Required** <br> The full webhook URL from Discord, see [here](https://discordjs.guide/legacy/popular-topics/webhooks) | |
| `CONTAINERS` | A comma-separated list of container names, or `*` for "everything" | `*` |
| `DOCKER_HOST` | If using socket-proxy you should pass the URI for it here. | |
| `EVENTS` | A comma separated list of events to watch. There are two special values, `all` for everything, or `default` for a smaller list (see separate table). | `default` |
| `EXTRA` | A string to send with every alert, perfect for sending @mentions for people. You need to obtain the ID (see [here](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID)) and format as `<@USER_ID>` or `<@&ROLE_ID>`, but can put any text here. | |
| `LOG_LEVEL` | How much to log: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` |
| `VERBOSE` | Provide more detail for the Discord messages. (`True` / `False`) | `False` |

## Docker Events

These are the supported docker events, and the colour of the notifications for each.

| Event | Description | Default |
| --- | --- | --- |
| `create` | ![#CCFFCC](https://placehold.co/15x15/CCFFCC/CCFFCC.png) ⏺️ Container Created | |
| `start` | ![#00FF00](https://placehold.co/15x15/00FF00/00FF00.png) ▶️ Container Started | ✅ |
| `pause` | ![#FFA500](https://placehold.co/15x15/FFA500/FFA500.png) ⏸️ Container Paused | ✅ |
| `unpause` | ![#A5FF00](https://placehold.co/15x15/A5FF00/A5FF00.png) ⏯️ Container Unpaused | ✅ |
| `restart` | ![#00FFA5](https://placehold.co/15x15/00FFA5/00FFA5.png) 🔁 Container Restarted *(will also show both `stop` and `start`)* | |
| `stop` | ![#CC0000](https://placehold.co/15x15/CC0000/CC0000.png) ⏹️ Container Stopped | ✅ |
| `kill` | ![#AA0000](https://placehold.co/15x15/AA0000/AA0000.png) 💀 Container Killed | |
| `die` | ![#FF0000](https://placehold.co/15x15/FF0000/FF0000.png) ⏏️ Container Died *(includes both `stop` and `kill`)* | |
| `health_status` | ![#712EFF](https://placehold.co/15x15/712EFF/712EFF.png) 🩺 Health Status | ✅ |
