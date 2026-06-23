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

        urls = settings.get('calendarURLs[]')
        colors = settings.get('calendarColors[]')
        
        if not urls:
            urls = ["https://www.calendarlabs.com/ical-calendar/ics/76/US_Holidays.ics"]
            colors = ["#000000"]
        elif not isinstance(urls, list):
            urls = [urls]
            colors = [colors]

        font_size = settings.get('fontSize', 'normal')

        # 1. Timeline (Left Quarter)
        cal_settings_timeline = {
            'calendarURLs[]': urls,
            'calendarColors[]': colors,
            'viewMode': 'timeGridDay',
            'language': 'en',
            'showDate': 'true',
            'displayWeekends': 'true',
            'fontSize': font_size
        }
        timeline_w = width // 4
        timeline_config = MockDeviceConfig(device_config, timeline_w, height)
        try:
            timeline_img = Calendar({"id": "calendar"}).generate_image(cal_settings_timeline, timeline_config)
            dashboard_image.paste(timeline_img, (0, 0))
        except Exception as e:
            logger.error(f"Timeline generation failed: {e}")

        # 2. Month Calendar (Right Side)
        weather_layout = settings.get('weatherLayout', 'full')

        right_w = width - timeline_w
        if weather_layout == 'none':
            month_h = height
        else:
            month_h = (height * 2) // 3

        cal_settings_month = {
            'calendarURLs[]': urls,
            'calendarColors[]': colors,
            'viewMode': 'dayGridMonth',
            'language': 'en',
            'showDate': 'true',
            'displayWeekends': 'true',
            'fontSize': font_size,
            'displayTitle': 'true',
            'displayEventTime': 'true'
        }
        month_config = MockDeviceConfig(device_config, right_w, month_h)
        try:
            month_img = Calendar({"id": "calendar"}).generate_image(cal_settings_month, month_config)
            dashboard_image.paste(month_img, (timeline_w, 0))
        except Exception as e:
            logger.error(f"Month calendar generation failed: {e}")

        if weather_layout != 'none':
            # 3. Weather (Bottom Right Third)
            weather_settings = {
                'latitude': settings.get('latitude', '40.7128'),
                'longitude': settings.get('longitude', '-74.0060'),
                'weatherProvider': 'OpenMeteo',
                'units': settings.get('units', 'imperial'),
                'titleSelection': 'custom',
                'customTitle': 'Weather',
                'weatherTimeZone': 'locationTimeZone',
                'fontSize': font_size,
                'displayMetrics': 'true'
            }

            if weather_layout == 'full':
                weather_settings.update({
                    'displayGraph': 'true',
                    'displayGraphIcons': 'true',
                    'displayRain': 'true',
                    'displayForecast': 'true',
                    'forecastDays': '5',
                    'moonPhase': 'true'
                })
            elif weather_layout == 'hourly':
                weather_settings.update({
                    'displayGraph': 'true',
                    'displayGraphIcons': 'true',
                    'displayRain': 'true',
                    'displayForecast': 'false'
                })
            elif weather_layout == 'forecast':
                weather_settings.update({
                    'displayGraph': 'false',
                    'displayForecast': 'true',
                    'forecastDays': '5',
                    'moonPhase': 'true'
                })
            weather_h = height - month_h
            weather_config = MockDeviceConfig(device_config, right_w, weather_h)
            try:
                weather_img = Weather({"id": "weather"}).generate_image(weather_settings, weather_config)
                dashboard_image.paste(weather_img, (timeline_w, month_h))
            except Exception as e:
                logger.error(f"Weather generation failed: {e}")

        # Draw dividing lines
        draw = ImageDraw.Draw(dashboard_image)
        # Vertical line at timeline boundary
        draw.line([(timeline_w, 0), (timeline_w, height)], fill="black", width=4)
        
        if weather_layout != 'none':
            # Horizontal line on the right side
            draw.line([(timeline_w, month_h), (width, month_h)], fill="black", width=4)

        return dashboard_image
