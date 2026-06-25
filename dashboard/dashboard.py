from plugins.base_plugin.base_plugin import BasePlugin
from plugins.calendar.calendar import Calendar
from plugins.weather.weather import Weather
from PIL import Image, ImageDraw, ImageOps
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

try:
    from plugins.todo_list.todo_list import TodoList
except ImportError:
    TodoList = None

try:
    from plugins.clock.clock import Clock
except ImportError:
    Clock = None

try:
    from plugins.wpotd.wpotd import Wpotd
except ImportError:
    Wpotd = None

try:
    from plugins.comic.comic import Comic
except ImportError:
    Comic = None


class OffsetCalendar(Calendar):
    """Utility subclass to render calendar events offset by N days for multi-day timeline grids."""
    def __init__(self, config, day_offset=0):
        super().__init__(config)
        self.day_offset = day_offset

    def get_view_range(self, view, current_dt, settings):
        shifted_dt = current_dt + timedelta(days=self.day_offset)
        return super().get_view_range(view, shifted_dt, settings)

    def render_image(self, dimensions, html_file, css_file=None, template_params={}):
        if self.day_offset != 0 and 'current_dt' in template_params:
            try:
                dt = datetime.fromisoformat(template_params['current_dt']) + timedelta(days=self.day_offset)
                template_params['current_dt'] = dt.isoformat()
            except Exception as e:
                logger.warning(f"Failed to shift current_dt in OffsetCalendar: {e}")
        return super().render_image(dimensions, html_file, css_file, template_params)


class Dashboard(BasePlugin):
    def generate_image(self, settings, device_config):
        # Target display size, handling display orientation from device config
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions

        # 1. Layout & Theme Configuration
        layout_preset = settings.get('layoutPreset', 'left_sidebar')
        theme_mode = settings.get('themeMode', 'light')
        show_dividers = settings.get('showDividers', 'true') == 'true'
        try:
            divider_thickness = int(settings.get('dividerThickness', '4'))
        except (ValueError, TypeError):
            divider_thickness = 4

        slot1_widget = settings.get('slot1Widget', 'timeline')
        slot2_widget = settings.get('slot2Widget', 'month')
        slot3_widget = settings.get('slot3Widget')
        
        # Backward compatibility with old weatherLayout settings
        if not slot3_widget:
            if settings.get('weatherLayout') == 'none':
                slot3_widget = 'none'
            else:
                slot3_widget = 'weather'

        bg_color = "white" if theme_mode != 'cards' else "#e4e4e7"
        dashboard_image = Image.new("RGB", (width, height), bg_color)

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

        # 2. Shared Data Sources (Calendars & Timezone)
        urls = settings.get('calendarURLs[]')
        colors = settings.get('calendarColors[]')
        if not urls:
            urls = ["https://www.calendarlabs.com/ical-calendar/ics/76/US_Holidays.ics"]
            colors = ["#000000"]
        elif not isinstance(urls, list):
            urls = [urls]
            colors = [colors]

        tz = pytz.timezone(settings.get("timezone", "UTC"))
        font_size = settings.get('fontSize', 'normal')

        # Dynamic Timeline Range Calculation
        min_hour, max_hour = self.calculate_timeline_hours(settings, urls, colors, tz)

        # 3. Calculate Slot Geometries: list of (widget_type, x, y, w, h)
        slots = []
        if layout_preset == 'left_sidebar':
            s1_w = width // 4
            s2_w = width - s1_w
            if slot3_widget == 'none':
                slots = [
                    (slot1_widget, 0, 0, s1_w, height),
                    (slot2_widget, s1_w, 0, s2_w, height)
                ]
            else:
                s2_h = (height * 2) // 3
                s3_h = height - s2_h
                slots = [
                    (slot1_widget, 0, 0, s1_w, height),
                    (slot2_widget, s1_w, 0, s2_w, s2_h),
                    (slot3_widget, s1_w, s2_h, s2_w, s3_h)
                ]
        elif layout_preset == 'right_sidebar':
            s3_w = width // 4
            main_w = width - s3_w
            if slot3_widget == 'none':
                slots = [
                    (slot1_widget, main_w, 0, s3_w, height),
                    (slot2_widget, 0, 0, main_w, height)
                ]
            else:
                s1_h = (height * 2) // 3
                s2_h = height - s1_h
                slots = [
                    (slot1_widget, main_w, 0, s3_w, height),
                    (slot2_widget, 0, 0, main_w, s1_h),
                    (slot3_widget, 0, s1_h, main_w, s2_h)
                ]
        elif layout_preset == 'even_split':
            if slot2_widget == 'none':
                slots = [(slot1_widget, 0, 0, width, height)]
            else:
                half_w = width // 2
                slots = [
                    (slot1_widget, 0, 0, half_w, height),
                    (slot2_widget, half_w, 0, width - half_w, height)
                ]
        elif layout_preset == 'three_column':
            c1_w = width // 3
            c2_w = width // 3
            c3_w = width - c1_w - c2_w
            slots = [
                (slot1_widget, 0, 0, c1_w, height),
                (slot2_widget, c1_w, 0, c2_w, height),
                (slot3_widget, c1_w + c2_w, 0, c3_w, height)
            ]
        elif layout_preset == 'top_banner':
            banner_h = height // 4
            bot_h = height - banner_h
            if slot3_widget == 'none':
                slots = [
                    (slot1_widget, 0, 0, width, banner_h),
                    (slot2_widget, 0, banner_h, width, bot_h)
                ]
            else:
                half_w = width // 2
                slots = [
                    (slot1_widget, 0, 0, width, banner_h),
                    (slot2_widget, 0, banner_h, half_w, bot_h),
                    (slot3_widget, half_w, banner_h, width - half_w, bot_h)
                ]

        # 4. Render and Paste Widgets
        for widget_type, sx, sy, sw, sh in slots:
            if sw <= 0 or sh <= 0 or widget_type == 'none' or not widget_type:
                continue

            pad = 8 if theme_mode == 'cards' else 0
            target_w = max(1, sw - 2 * pad)
            target_h = max(1, sh - 2 * pad)

            widget_img = self.generate_widget_image(
                widget_type, target_w, target_h, settings, device_config,
                urls, colors, tz, min_hour, max_hour, font_size, theme_mode
            )

            if widget_img:
                if theme_mode == 'cards':
                    mask = Image.new("L", (target_w, target_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle((0, 0, target_w, target_h), radius=12, fill=255)
                    dashboard_image.paste(widget_img, (sx + pad, sy + pad), mask=mask)
                else:
                    dashboard_image.paste(widget_img, (sx, sy))

        # 5. Draw Dividing Lines (if applicable)
        if show_dividers and theme_mode != 'cards':
            draw = ImageDraw.Draw(dashboard_image)
            line_color = "black"
            lw = divider_thickness

            if layout_preset == 'left_sidebar':
                x_split = width // 4
                draw.line([(x_split, 0), (x_split, height)], fill=line_color, width=lw)
                if slot3_widget != 'none':
                    y_split = (height * 2) // 3
                    draw.line([(x_split, y_split), (width, y_split)], fill=line_color, width=lw)
            elif layout_preset == 'right_sidebar':
                x_split = width - width // 4
                draw.line([(x_split, 0), (x_split, height)], fill=line_color, width=lw)
                if slot3_widget != 'none':
                    y_split = (height * 2) // 3
                    draw.line([(0, y_split), (x_split, y_split)], fill=line_color, width=lw)
            elif layout_preset == 'even_split' and slot2_widget != 'none':
                x_split = width // 2
                draw.line([(x_split, 0), (x_split, height)], fill=line_color, width=lw)
            elif layout_preset == 'three_column':
                c1_w = width // 3
                c2_w = width // 3
                draw.line([(c1_w, 0), (c1_w, height)], fill=line_color, width=lw)
                draw.line([(c1_w + c2_w, 0), (c1_w + c2_w, height)], fill=line_color, width=lw)
            elif layout_preset == 'top_banner':
                banner_h = height // 4
                draw.line([(0, banner_h), (width, banner_h)], fill=line_color, width=lw)
                if slot3_widget != 'none':
                    half_w = width // 2
                    draw.line([(half_w, banner_h), (half_w, height)], fill=line_color, width=lw)

        # 6. Apply Theme Inversion for Dark Mode
        if theme_mode == 'dark':
            dashboard_image = ImageOps.invert(dashboard_image)

        return dashboard_image

    def calculate_timeline_hours(self, settings, urls, colors, tz):
        user_start = int(settings.get('startTimeInterval', '6'))
        user_end = int(settings.get('endTimeInterval', '22'))
        min_hour = user_start
        max_hour = user_end

        try:
            now = datetime.now(tz)
            start_range = datetime(now.year, now.month, now.day, tzinfo=tz)
            timeline_days = int(settings.get('timelineDays', '1'))
            end_range = start_range + timedelta(days=timeline_days)

            cal_instance = Calendar({"id": "calendar"})
            events = cal_instance.fetch_ics_events(urls, colors, tz, start_range, end_range)

            for event in events:
                if not event.get('allDay'):
                    start_dt = datetime.fromisoformat(event['start'])
                    if start_dt.hour < min_hour:
                        min_hour = start_dt.hour

                    if 'end' in event:
                        end_dt = datetime.fromisoformat(event['end'])
                        end_h = end_dt.hour
                        if end_dt.minute > 0:
                            end_h += 1
                        if end_h > max_hour:
                            max_hour = end_h
        except Exception as e:
            logger.error(f"Failed to calculate dynamic time interval: {e}")

        min_hour = max(0, min_hour)
        max_hour = min(24, max_hour)
        if max_hour <= min_hour:
            max_hour = min_hour + 1
        return min_hour, max_hour

    def generate_widget_image(self, widget_type, w, h, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode):
        class MockChildConfig:
            def __init__(self, orig, cw, ch):
                self.orig = orig
                self.cw = cw
                self.ch = ch
            def get_resolution(self):
                return (self.cw, self.ch)
            def get_config(self, k, default=None):
                if k == "orientation":
                    return "horizontal"
                return self.orig.get_config(k, default)
            def load_env_key(self, k):
                return self.orig.load_env_key(k)

        mock_config = MockChildConfig(device_config, w, h)

        try:
            if widget_type == 'timeline':
                timeline_days = int(settings.get('timelineDays', '1'))
                cal_settings = {
                    'calendarURLs[]': urls,
                    'calendarColors[]': colors,
                    'viewMode': 'timeGridDay',
                    'language': settings.get('language', 'en'),
                    'showDate': 'true',
                    'displayWeekends': 'true',
                    'fontSize': font_size,
                    'startTimeInterval': str(min_hour),
                    'endTimeInterval': str(max_hour)
                }
                if timeline_days <= 1:
                    return Calendar({"id": "calendar"}).generate_image(cal_settings, mock_config)
                else:
                    combined_img = Image.new("RGB", (w, h), "white")
                    day_w = w // timeline_days
                    for i in range(timeline_days):
                        cur_w = day_w if i < timeline_days - 1 else w - i * day_w
                        sub_config = MockChildConfig(device_config, cur_w, h)
                        sub_cal = OffsetCalendar({"id": "calendar"}, day_offset=i)
                        sub_img = sub_cal.generate_image(cal_settings, sub_config)
                        if sub_img:
                            combined_img.paste(sub_img, (i * day_w, 0))
                    return combined_img

            elif widget_type == 'agenda':
                agenda_settings = {
                    'calendarURLs[]': urls,
                    'calendarColors[]': colors,
                    'viewMode': 'listMonth',
                    'language': settings.get('language', 'en'),
                    'showDate': 'true',
                    'fontSize': font_size,
                    'displayTitle': 'true',
                    'displayEventTime': 'true'
                }
                return Calendar({"id": "calendar"}).generate_image(agenda_settings, mock_config)

            elif widget_type == 'month':
                month_settings = {
                    'calendarURLs[]': urls,
                    'calendarColors[]': colors,
                    'viewMode': 'dayGridMonth',
                    'language': settings.get('language', 'en'),
                    'showDate': 'true',
                    'displayWeekends': 'true',
                    'fontSize': font_size,
                    'displayTitle': 'true',
                    'displayEventTime': 'true'
                }
                return Calendar({"id": "calendar"}).generate_image(month_settings, mock_config)

            elif widget_type == 'weather':
                weather_layout = settings.get('weatherLayout', 'full')
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
                return Weather({"id": "weather"}).generate_image(weather_settings, mock_config)

            elif widget_type == 'todo':
                if not TodoList:
                    raise RuntimeError("TodoList plugin is not installed")
                todo_title = settings.get('todoTitle', 'Tasks')
                todo_items = settings.get('todoItems', 'Review schedule\nCheck emails\nUpdate dashboard')
                todo_settings = {
                    'title': todo_title,
                    'listStyle': 'disc',
                    'fontSize': font_size,
                    'list-title[]': [todo_title],
                    'list[]': [todo_items]
                }
                return TodoList({"id": "todo_list"}).generate_image(todo_settings, mock_config)

            elif widget_type == 'clock':
                if not Clock:
                    raise RuntimeError("Clock plugin is not installed")
                clock_settings = {
                    'selectedClockFace': settings.get('clockFace', 'Gradient Clock'),
                    'primaryColor': '#ffffff' if theme_mode == 'light' else '#000000',
                    'secondaryColor': '#000000' if theme_mode == 'light' else '#ffffff'
                }
                return Clock({"id": "clock"}).generate_image(clock_settings, mock_config)

            elif widget_type == 'wpotd':
                if not Wpotd:
                    raise RuntimeError("Wpotd plugin is not installed")
                wpotd_settings = {
                    'randomizeWpotd': 'false',
                    'shrinkToFitWpotd': 'true'
                }
                return Wpotd({"id": "wpotd"}).generate_image(wpotd_settings, mock_config)

            elif widget_type == 'comic':
                if not Comic:
                    raise RuntimeError("Comic plugin is not installed")
                comic_settings = {
                    'comic': settings.get('comicSelection', 'xkcd'),
                    'titleCaption': 'true',
                    'fontSize': font_size
                }
                return Comic({"id": "comic"}).generate_image(comic_settings, mock_config)

        except Exception as e:
            logger.error(f"Failed to generate widget '{widget_type}': {e}")
            err_img = Image.new("RGB", (w, h), "white")
            draw = ImageDraw.Draw(err_img)
            draw.text((10, 10), f"[{widget_type} Error]", fill="black")
            return err_img

        return None
