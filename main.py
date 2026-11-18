import docker
import requests
import json
import time
import os
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import logging

logging.basicConfig(
    level = os.getenv('LOG_LEVEL', 'INFO'),
    format = '[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Events that mean a container is going down, and might be coming straight back up
DOWN_EVENTS = ('kill', 'die', 'stop')

@dataclass
class EventConfig:
    title: str
    description: str
    color: int

@dataclass
class ImageInfo:
    id: str
    tag: str
    version: Optional[str]

    def describe(self) -> str:
        short = self.id.split(':')[-1][:12]
        return f"{self.version} ({short})" if self.version else short

@dataclass
class Notification:
    action: str
    name: str
    fields: List[Dict[str, Any]]

@dataclass
class PendingDown:
    """A container that has gone down, held back in case it comes straight back up."""
    image: Optional[ImageInfo]
    notifications: List[Notification] = field(default_factory=list)
    exit_code: Optional[str] = None
    timer: Optional[threading.Timer] = None

class DockerMonitor:
    def __init__(self):
        # Get configuration from environment variables
        self.webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

        # Container monitoring configuration
        containers = os.environ.get('CONTAINERS', '*')
        self.containers = [x.strip() for x in containers.split(',')]

        # Verbose monitoring configuration
        self.verbose = os.getenv("VERBOSE", 'False').lower() in ('true', '1', 't')

        # Extra text to add to notifications
        self.extra = os.environ.get('EXTRA', '')

        # Health check configuration
        self.health_check_interval = int(os.environ.get('HEALTH_CHECK_INTERVAL', '300'))  # Default 5 minutes

        # Configure retry settings for Discord webhook
        self.max_retries = int(os.environ.get('MAX_RETRIES', '3'))
        self.retry_delay = int(os.environ.get('RETRY_DELAY', '5'))

        # How long to wait after a container goes down to see if it comes back up (0 to disable)
        self.restart_window = float(os.environ.get('RESTART_WINDOW', '30'))

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
            'update': EventConfig(
                title="\⬆️ Container Updated: {name}",
                description="Container {name} has been restarted with a new image.",
                color=0x00A5FF
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
            events = 'start,pause,unpause,restart,update,stop,health_status'

        self.events = list(self.event_configs.keys()) if events == 'all' else [x.strip() for x in events.split(',')]

        for action in self.events:
            if action not in self.event_configs.keys():
                logger.warning(f"Unknown event type: {action}")

        # Containers that have gone down and might be coming back up, by name
        self.pending: Dict[str, PendingDown] = {}
        # When a combined restart / update was last sent, by name, so the native `restart` event can be skipped
        self.combined_at: Dict[str, float] = {}
        # The image each container was last seen running, by name
        self.images: Dict[str, ImageInfo] = {}
        self.lock = threading.Lock()

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

    def get_image_info(self, container) -> Optional[ImageInfo]:
        """Get the image a container is running, with its version label if it has one."""
        try:
            image_id = container.attrs.get('Image')
            if not image_id:
                return None
            tag = container.attrs.get('Config', {}).get('Image') or 'untagged'
            version = None
            try:
                image = self.client.images.get(image_id)
                version = (image.labels or {}).get('org.opencontainers.image.version')
            except Exception:
                pass # The image may have been removed already
            return ImageInfo(id=image_id, tag=tag, version=version)
        except Exception as e:
            logger.debug(f"Error getting image info: {e}")
            return None

    def remember_image(self, name: str, container_id: str) -> Optional[ImageInfo]:
        """Record the image a container is using, so we can tell if it changes later."""
        try:
            info = self.get_image_info(self.client.containers.get(container_id))
        except Exception as e:
            logger.debug(f"Error getting container {name}: {e}")
            return None
        if info:
            with self.lock:
                self.images[name] = info
        return info

    def load_images(self) -> None:
        """Record the image for every existing container, so the first update can be spotted."""
        try:
            for container in self.client.containers.list(all=True):
                info = self.get_image_info(container)
                if info:
                    self.images[container.name] = info
        except Exception as e:
            logger.warning(f"Unable to list existing containers: {e}")

    def build_notification(self, action: str, name: str, container_id: str, event: Dict[str, Any]) -> Notification:
        """Build the fields for a single event notification."""
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

        return Notification(action=action, name=name, fields=fields)

    def send_notification(self, notification: Notification) -> None:
        event_config = self.event_configs[notification.action]
        if not self.send_discord_embed(
            event_config.title.format(name=notification.name),
            event_config.description.format(name=notification.name),
            event_config.color,
            notification.fields
        ):
            logger.error(f"Failed to send notification for {notification.name} {notification.action}")

    def flush_pending(self, name: str) -> None:
        """The container didn't come back up in time, so send what was held back."""
        with self.lock:
            pending = self.pending.pop(name, None)
        if pending:
            logger.debug(f"No restart for {name}, sending {len(pending.notifications)} held notifications")
            for notification in pending.notifications:
                self.send_notification(notification)

    def hold_down_event(self, action: str, name: str, container_id: str, event: Dict[str, Any]) -> None:
        """Hold back a container going down, in case it is just restarting."""
        notification = self.build_notification(action, name, container_id, event) if action in self.events else None
        with self.lock:
            pending = self.pending.get(name)
            if not pending:
                pending = PendingDown(image=self.images.get(name))
                pending.timer = threading.Timer(self.restart_window, self.flush_pending, args=(name,))
                pending.timer.daemon = True
                pending.timer.start()
                self.pending[name] = pending
            if action == 'die':
                pending.exit_code = event['Actor']['Attributes'].get('exitCode')
            if notification:
                pending.notifications.append(notification)

    def handle_start(self, name: str, container_id: str, event: Dict[str, Any]) -> None:
        """A container has started, combine it with any held back down events."""
        with self.lock:
            pending = self.pending.pop(name, None)
        if pending and pending.timer:
            pending.timer.cancel()

        previous = pending.image if pending else None
        current = self.remember_image(name, container_id)

        if pending:
            updated = previous is not None and current is not None and previous.id != current.id
            action = 'update' if updated else 'restart'

            if action in self.events:
                notification = self.build_notification(action, name, container_id, event)
                extra_fields = []
                if updated:
                    extra_fields.append({"name": "Image", "value": f"`{current.tag}`", "inline": False})
                    extra_fields.append({"name": "Version", "value": f"`{previous.describe()}` → `{current.describe()}`", "inline": False})
                if pending.exit_code not in (None, '0'):
                    extra_fields.append({"name": "Exit Code", "value": pending.exit_code, "inline": False})
                # Keep the timestamp last
                notification.fields[-1:-1] = extra_fields
                with self.lock:
                    self.combined_at[name] = time.time()
                self.send_notification(notification)
                return

            # Not combining these, so send them as they happened
            for notification in pending.notifications:
                self.send_notification(notification)

        if 'start' in self.events:
            self.send_notification(self.build_notification('start', name, container_id, event))

    def monitor_events(self) -> None:
        """Monitor Docker events and send notifications."""
        logger.info(f"Starting Docker monitor for events: {','.join(self.events)}")
        logger.info(f"Monitoring containers: {','.join(self.containers)}")
        if self.restart_window > 0:
            logger.info(f"Combining restarts within {self.restart_window:g} seconds")
            self.load_images()

        try:
            all_containers = '*' in self.containers
            for event in self.client.events(decode=True):
                if event['Type'] != 'container':
                    continue

                container_name = event['Actor']['Attributes'].get('name', 'unknown')

                # Skip if container is not in monitored list, or we're watching for everything except it
                if all_containers:
                    if '-' + container_name in self.containers:
                        continue
                elif container_name not in self.containers:
                    continue

                action = event['Action']
                container_id = event['id'] if 'id' in event else event['Actor']['ID']

                if self.restart_window > 0:
                    if action in DOWN_EVENTS:
                        logger.debug(event)
                        self.hold_down_event(action, container_name, container_id, event)
                        continue

                    if action == 'create':
                        with self.lock:
                            pending = self.pending.get(container_name)
                        if pending:
                            # Being recreated (ie, watchtower or compose), so hold it with the down events
                            if action in self.events:
                                pending.notifications.append(self.build_notification(action, container_name, container_id, event))
                            continue

                    if action == 'start':
                        logger.debug(event)
                        self.handle_start(container_name, container_id, event)
                        continue

                    if action == 'restart':
                        with self.lock:
                            combined_at = self.combined_at.pop(container_name, 0)
                        if time.time() - combined_at < self.restart_window:
                            logger.debug(f"Skipping restart for {container_name}, already sent")
                            continue

                # Skip if action is not in notification level
                if action not in self.events:
                    logger.debug(f"Skipping event: {action}")
                    continue

                if action in self.event_configs:
                    logger.debug(event)
                    self.send_notification(self.build_notification(action, container_name, container_id, event))

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
