import docker
import requests
import json
import time
import os
from typing import Dict, List, Any
from dataclasses import dataclass
import logging

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class EventConfig:
    title: str
    description: str
    color: int

class DockerMonitor:
    def __init__(self):
        # Get configuration from environment variables
        self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

        # Container monitoring configuration
        self.containers = os.environ.get('CONTAINERS', '*')

        # Verbose monitoring configuration
        self.verbose = os.getenv("VERBOSE", 'False').lower() in ('true', '1', 't')

        # Extra text to add to notifications
        self.extra = os.environ.get('EXTRA', '')

        # Health check configuration
        self.health_check_interval = int(os.environ.get('HEALTH_CHECK_INTERVAL', '300'))  # Default 5 minutes

        # Configure retry settings for Discord webhook
        self.max_retries = int(os.environ.get('MAX_RETRIES', '3'))
        self.retry_delay = int(os.environ.get('RETRY_DELAY', '5'))

        try:
            self.client = docker.from_env()
            # Test Docker connection
            self.client.ping()
        except docker.errors.DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise

        # Event configurations with emoji support
        self.event_configs = {
            'create': EventConfig(
                title="\⏺️ Container Created: {name}",
                description="Container {name} was created successfully.",
                color=0xCCFFCC
            ),
            'start': EventConfig(
                title="\▶️ Container Started: {name}",
                description="Container {name} has started successfully.",
                color=0x00FF00
            ),
            'pause': EventConfig(
                title="\⏸️ Container Paused: {name}",
                description="Container {name} has been paused.",
                color=0xFFA500
            ),
            'unpause': EventConfig(
                title="\⏯️ Container Unpaused: {name}",
                description="Container {name} has been unpaused.",
                color=0xA5FF00
            ),
            'restart': EventConfig(
                title="\🔁 Container Restarted: {name}",
                description="Container {name} has been restarted.",
                color=0x00FFA5
            ),
            'stop': EventConfig(
                title="\⏹️ Container Stopped: {name}",
                description="Container {name} has stopped.",
                color=0xCC0000
            ),
            'kill': EventConfig(
                title="\💀 Container Killed: {name}",
                description="Container {name} has been killed.",
                color=0xAA0000
            ),
            'die': EventConfig(
                title="\⏏️ Container Died: {name}",
                description="Container {name} has died.",
                color=0xFF0000
            ),
            'health_status': EventConfig(
                title="\🩺 Health Status: {name}",
                description="Health status changed for container {name}.",
                color=0x712EFF
            )
        }

        # Event monitoring configuration
        events = os.environ.get('EVENTS', 'default').lower()

        if events == 'default':
            events = 'start,pause,unpause,stop,restart,health_status'

        self.events = list(self.event_configs.keys()) if events == 'all' else [x.strip() for x in events.split(',')]

        for action in self.events:
            if action not in self.event_configs.keys():
                logger.warning(f"Unknown event type: {action}")

    def send_discord_embed(self, title: str, description: str, color: int, fields: List[Dict[str, Any]]) -> bool:
        """Send an embed message to Discord webhook with retries."""
        embed = {
            "title": title,
            "color": color,
            "fields": fields
        }

        # This simply duplicates the title, so save vertical space
        if self.verbose:
            embed['description'] = description + ('\n' + self.extra if self.extra else '')
        elif self.extra:
            embed['description'] = self.extra

        payload = {"embeds": [embed]}
        headers = {"Content-Type": "application/json"}

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 204:
                    return True
                logger.warning(f"Discord API returned status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue
        return False

    def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """Get detailed container status information."""
        try:
            container = self.client.containers.get(container_id)
            status = {
                "image": container.image.tags[0] if container.image.tags else "untagged",
                "status": container.status,
                "health": container.attrs.get('State', {}).get('Health', {}).get('Status', 'N/A'),
                "created": container.attrs['Created'][:19].replace('T', ' '),
                "platform": container.attrs.get('Platform', 'N/A')
            }
            return status
        except docker.errors.NotFound:
            return {"image": "unknown", "status": "unknown", "health": "unknown", "created": "unknown", "platform": "unknown"}
        except Exception as e:
            logger.error(f"Error getting container status: {e}")
            return {"image": "error", "status": "error", "health": "error", "created": "error", "platform": "error"}

    def monitor_events(self) -> None:
        """Monitor Docker events and send notifications."""
        logger.info(f"Starting Docker monitor for events: {','.join(self.events)}")
        logger.info(f"Monitoring containers: {self.containers}")

        try:
            for event in self.client.events(decode=True):
                if event['Type'] != 'container':
                    continue

                container_name = event['Actor']['Attributes'].get('name', 'unknown')
                action = event['Action']

                # Skip if container is not in monitored list
                if self.containers != '*' and container_name not in self.containers.split(','):
                    continue

                # Skip if action is not in notification level
                if action not in self.events:
                    continue

                if action in self.event_configs:
                    container_id = event['id'] if 'id' in event else event['Actor']['ID']
                    status = self.get_container_status(container_id)

                    fields = [
                        {"name": "Event", "value": f"`{action}`", "inline": True},
                        {"name": "Status", "value": f"`{status["status"]}`", "inline": True},
                        {"name": "Health", "value": f"`{status["health"]}`", "inline": True},
                        {"name": "Image", "value": f"`{status["image"]}`", "inline": True},
                        {"name": "Platform", "value": f"`{status["platform"]}`", "inline": True},
                    ] if self.verbose else []

                    if action == 'die':
                        # Add exit code for stopped containers
                        exit_code = event['Actor']['Attributes'].get('exitCode', 'Unknown')
                        fields.append({
                            "name": "Exit Code",
                            "value": exit_code,
                            "inline": False
                        })
                    elif action == 'health_status' and not self.verbose:
                        # Health status has now changed
                        fields.append({
                            "name": "Health",
                            "value": status["health"],
                            "inline": True
                        })

                    fields.append({
                        "name": "Timestamp",
                        "value": f"<t:{int(time.time())}:F>",
                        "inline": False
                    })

                    event_config = self.event_configs[action]
                    if not self.send_discord_embed(
                        event_config.title.format(name=container_name),
                        event_config.description.format(name=container_name),
                        event_config.color,
                        fields
                    ):
                        logger.error(f"Failed to send notification for {container_name} {action}")

        except KeyboardInterrupt:
            logger.info("Gracefully shutting down Docker monitor...")
        except Exception as e:
            logger.error(f"Fatal error in event monitoring: {e}")
            raise

def main():
    try:
        monitor = DockerMonitor()
        monitor.monitor_events()
    except Exception as e:
        logger.error(f"Application error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
