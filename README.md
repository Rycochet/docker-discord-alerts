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
- **Whitelist or Blacklist**: Only monitor the containers you want to.
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
| `CONTAINERS` | A comma-separated list of container names, or `*` for "everything". <br> If you use `*` then you can **also** ignore specific containers by prefixing with a dash, ie `*,-hello-world` would show all containers *except* `hello-world`. | `*` |
| `DOCKER_HOST` | If using socket-proxy you should pass the URI for it here. | |
| `EVENTS` | A comma separated list of events to watch. There are two special values, `all` for everything, or `default` for a smaller list (see separate table). | `default` |
| `EXTRA` | A string to send with every alert, perfect for sending @mentions for people. You need to obtain the ID (see [here](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID)) and format as `<@USER_ID>` or `<@&ROLE_ID>`, but can put any text here. | |
| `LOG_LEVEL` | How much to log: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` |
| `RESTART_WINDOW` | Seconds to wait after a container goes down (`kill`, `die` or `stop`) to see if it comes back up. If it starts again within this time a single `restart` or `update` alert is sent instead of separate down and up alerts (see below). Set to `0` to turn this off and send every event straight away. | `30` |
| `VERBOSE` | Provide more detail for the Discord messages. (`True` / `False`) | `False` |

## Docker Events

These are the supported docker events, and the colour of the notifications for each.

| Event | Description | Default |
| --- | --- | --- |
| `create` | ![#CCFFCC](https://placehold.co/15x15/CCFFCC/CCFFCC.png) ⏺️ Container Created | |
| `start` | ![#00FF00](https://placehold.co/15x15/00FF00/00FF00.png) ▶️ Container Started | ✅ |
| `pause` | ![#FFA500](https://placehold.co/15x15/FFA500/FFA500.png) ⏸️ Container Paused | ✅ |
| `unpause` | ![#A5FF00](https://placehold.co/15x15/A5FF00/A5FF00.png) ⏯️ Container Unpaused | ✅ |
| `restart` | ![#00FFA5](https://placehold.co/15x15/00FFA5/00FFA5.png) 🔁 Container Restarted *(same image, includes the exit code if it crashed)* | ✅ |
| `update` | ![#00A5FF](https://placehold.co/15x15/00A5FF/00A5FF.png) ⬆️ Container Updated *(restarted with a new image, ie by Watchtower)* | ✅ |
| `stop` | ![#CC0000](https://placehold.co/15x15/CC0000/CC0000.png) ⏹️ Container Stopped | ✅ |
| `kill` | ![#AA0000](https://placehold.co/15x15/AA0000/AA0000.png) 💀 Container Killed | |
| `die` | ![#FF0000](https://placehold.co/15x15/FF0000/FF0000.png) ⏏️ Container Died *(includes both `stop` and `kill`)* | |
| `health_status` | ![#712EFF](https://placehold.co/15x15/712EFF/712EFF.png) 🩺 Health Status | ✅ |

### Restarts and Updates

When a container goes down, the alert is held back for `RESTART_WINDOW` seconds. If a container with the same name starts again in that time, the held alerts and the `start` alert are replaced by one alert:

- **Updated** if the new container is running a different image (such as after Watchtower or `docker compose up -d` pulls a new version). This shows the image, and the old and new versions - taken from the `org.opencontainers.image.version` label when the image has one, along with the short image ID.
- **Restarted** if it is the same image. If the container crashed (a non-zero exit code) then that is included.

If the matching event (`restart` or `update`) is not in `EVENTS` then the held alerts are sent as they happened instead. A container that stays down is still reported, just `RESTART_WINDOW` seconds later.
