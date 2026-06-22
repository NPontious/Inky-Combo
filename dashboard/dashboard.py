from plugins.base_plugin.base_plugin import BasePlugin
from plugins.calendar.calendar import Calendar
from plugins.weather.weather import Weather
from PIL import Image, ImageDraw
import logging

logger = logging.getLogger(__name__)

class Dashboard(BasePlugin):
    def generate_image(self, settings, device_config):
        # Target display size, handling display orientation from device config
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions

        # Create a blank image (white background)
        dashboard_image = Image.new("RGB", (width, height), "white")

        # Utility class to mock device configuration for child plugins
        class MockDeviceConfig:
            def __init__(self, original_config, w, h):
                self.original_config = original_config
                self.w = w
                self.h = h

            def get_resolution(self):
                return (self.w, self.h)

            def get_config(self, key, default=None):
                if key == "orientation":
                    return "horizontal"
                return self.original_config.get_config(key, default)
                
            def load_env_key(self, key):
                return self.original_config.load_env_key(key)

        calendar_url = settings.get("calendarUrl")
        if not calendar_url:
            calendar_url = "https://www.calendarlabs.com/ical-calendar/ics/76/US_Holidays.ics"

        # 1. Timeline (Left half)
        cal_settings_timeline = {
            'calendarURLs[]': [calendar_url],
            'calendarColors[]': ['#000000'],
            'viewMode': 'timeGridDay',
            'language': 'en',
            'showDate': 'true'
        }
        timeline_config = MockDeviceConfig(device_config, width // 2, height)
        try:
            timeline_img = Calendar({"id": "calendar"}).generate_image(cal_settings_timeline, timeline_config)
            dashboard_image.paste(timeline_img, (0, 0))
        except Exception as e:
            logger.error(f"Timeline generation failed: {e}")

        # 2. Month Calendar (Top Right)
        cal_settings_month = {
            'calendarURLs[]': [calendar_url],
            'calendarColors[]': ['#000000'],
            'viewMode': 'dayGridMonth',
            'language': 'en',
            'showDate': 'true'
        }
        month_config = MockDeviceConfig(device_config, width // 2, height // 2)
        try:
            month_img = Calendar({"id": "calendar"}).generate_image(cal_settings_month, month_config)
            dashboard_image.paste(month_img, (width // 2, 0))
        except Exception as e:
            logger.error(f"Month calendar generation failed: {e}")

        # 3. Weather (Bottom Right)
        weather_settings = {
            'latitude': settings.get('latitude', '40.7128'),
            'longitude': settings.get('longitude', '-74.0060'),
            'weatherProvider': 'OpenMeteo',
            'units': settings.get('units', 'imperial'),
            'titleSelection': 'custom',
            'customTitle': 'Weather',
            'weatherTimeZone': 'locationTimeZone'
        }
        weather_config = MockDeviceConfig(device_config, width // 2, height // 2)
        try:
            weather_img = Weather({"id": "weather"}).generate_image(weather_settings, weather_config)
            dashboard_image.paste(weather_img, (width // 2, height // 2))
        except Exception as e:
            logger.error(f"Weather generation failed: {e}")

        # Draw dividing lines
        draw = ImageDraw.Draw(dashboard_image)
        # Vertical line down the middle
        draw.line([(width // 2, 0), (width // 2, height)], fill="black", width=4)
        # Horizontal line on the right side
        draw.line([(width // 2, height // 2), (width, height // 2)], fill="black", width=4)

        return dashboard_image
