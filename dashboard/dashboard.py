from plugins.base_plugin.base_plugin import BasePlugin, BASE_PLUGIN_RENDER_DIR, STATIC_DIR, get_fonts, take_screenshot_html
from plugins.calendar.calendar import Calendar
from plugins.weather.weather import Weather
from PIL import Image, ImageDraw, ImageOps
import logging
import json
import os
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


class MultiDayCalendar(Calendar):
    """Unified multi-day timeline calendar ensuring perfect Y-axis and grid line alignment across days."""
    def __init__(self, config, days=1):
        super().__init__(config)
        self.days = max(1, int(days))

    def get_view_range(self, view, current_dt, settings):
        start = datetime(current_dt.year, current_dt.month, current_dt.day, tzinfo=current_dt.tzinfo)
        end = start + timedelta(days=self.days)
        return start, end

    def generate_image(self, settings, device_config):
        orig_view = settings.get("viewMode")
        settings["viewMode"] = "timeGridDay"
        try:
            return super().generate_image(settings, device_config)
        finally:
            if orig_view:
                settings["viewMode"] = orig_view

    def render_image(self, dimensions, html_file, css_file=None, template_params={}):
        css_files = [os.path.join(BASE_PLUGIN_RENDER_DIR, "plugin.css")]
        if css_file:
            plugin_css = os.path.join(self.render_dir, css_file)
            css_files.append(plugin_css)

        template_params["style_sheets"] = css_files
        template_params["width"] = dimensions[0]
        template_params["height"] = dimensions[1]
        template_params["font_faces"] = get_fonts()
        template_params["static_dir"] = STATIC_DIR

        template = self.env.get_template(html_file)
        rendered_html = template.render(template_params)

        custom_fc_init = f"""
            views: {{
                customMultiDay: {{
                    type: 'timeGrid',
                    duration: {{ days: {self.days} }}
                }}
            }},
            initialView: 'customMultiDay',
        """
        rendered_html = rendered_html.replace("initialView: 'timeGridDay',", custom_fc_init)

        google_style_css = """
        <style>
        .fc-timegrid-col-events { margin: 0 4px !important; }
        .fc-event { border-radius: 6px !important; border: none !important; box-shadow: 0 1px 2px rgba(0,0,0,0.12); }
        .fc-col-header-cell { padding: 6px 0 !important; font-weight: 700 !important; }
        </style>
        """
        rendered_html += google_style_css

        return take_screenshot_html(rendered_html, dimensions)


class Dashboard(BasePlugin):
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions

        theme_mode = settings.get('themeMode', 'light')
        show_dividers = settings.get('showDividers', 'true') == 'true'
        try:
            divider_thickness = int(settings.get('dividerThickness', '4'))
        except (ValueError, TypeError):
            divider_thickness = 4

        bg_color = "white" if theme_mode != 'cards' else "#e4e4e7"
        dashboard_image = Image.new("RGB", (width, height), bg_color)

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

        # 1. Resolve Layout Tree
        tree_root = self.get_layout_tree(settings)

        # 2. Dynamic Timeline Range Calculation
        active_widgets = self.get_active_widgets(tree_root)
        if 'timeline' in active_widgets:
            min_hour, max_hour = self.calculate_timeline_hours(settings, urls, colors, tz)
        else:
            min_hour, max_hour = 6, 22

        # 3. Recursively Render Tree onto Dashboard Canvas
        self.render_node(
            tree_root, 0, 0, width, height, settings, device_config,
            urls, colors, tz, min_hour, max_hour, font_size, theme_mode,
            dashboard_image, show_dividers, divider_thickness
        )

        # 4. Apply Theme Inversion for Dark Mode
        if theme_mode == 'dark':
            dashboard_image = ImageOps.invert(dashboard_image)

        return dashboard_image

    def get_active_widgets(self, node):
        if not node:
            return []
        if node.get("type") == "widget":
            return [node.get("widget")]
        return self.get_active_widgets(node.get("first")) + self.get_active_widgets(node.get("second"))

    def get_layout_tree(self, settings):
        tree_str = settings.get('layoutTree')
        if tree_str:
            try:
                return json.loads(tree_str)
            except Exception as e:
                logger.warning(f"Failed to parse layoutTree JSON: {e}")

        preset = settings.get('layoutPreset', 'left_sidebar')
        s1 = settings.get('slot1Widget', 'timeline')
        s2 = settings.get('slot2Widget', 'month')
        s3 = settings.get('slot3Widget')
        if not s3:
            s3 = 'none' if settings.get('weatherLayout') == 'none' else 'weather'

        if preset == 'even_split':
            return {
                "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 50,
                "first": {"id": "n1", "type": "widget", "widget": s1},
                "second": {"id": "n2", "type": "widget", "widget": s2}
            }
        elif preset == 'three_column':
            return {
                "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 33,
                "first": {"id": "n1", "type": "widget", "widget": s1},
                "second": {
                    "id": "n2", "type": "split", "direction": "horizontal", "splitRatio": 50,
                    "first": {"id": "n3", "type": "widget", "widget": s2},
                    "second": {"id": "n4", "type": "widget", "widget": s3}
                }
            }
        elif preset == 'right_sidebar':
            if s3 == 'none':
                return {
                    "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 75,
                    "first": {"id": "n1", "type": "widget", "widget": s2},
                    "second": {"id": "n2", "type": "widget", "widget": s1}
                }
            return {
                "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 75,
                "first": {
                    "id": "n1", "type": "split", "direction": "vertical", "splitRatio": 66,
                    "first": {"id": "n2", "type": "widget", "widget": s2},
                    "second": {"id": "n3", "type": "widget", "widget": s3}
                },
                "second": {"id": "n4", "type": "widget", "widget": s1}
            }
        elif preset == 'top_banner':
            if s3 == 'none':
                return {
                    "id": "root", "type": "split", "direction": "vertical", "splitRatio": 25,
                    "first": {"id": "n1", "type": "widget", "widget": s1},
                    "second": {"id": "n2", "type": "widget", "widget": s2}
                }
            return {
                "id": "root", "type": "split", "direction": "vertical", "splitRatio": 25,
                "first": {"id": "n1", "type": "widget", "widget": s1},
                "second": {
                    "id": "n2", "type": "split", "direction": "horizontal", "splitRatio": 50,
                    "first": {"id": "n3", "type": "widget", "widget": s2},
                    "second": {"id": "n4", "type": "widget", "widget": s3}
                }
            }
        else: # left_sidebar default
            if s3 == 'none':
                return {
                    "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 25,
                    "first": {"id": "n1", "type": "widget", "widget": s1},
                    "second": {"id": "n2", "type": "widget", "widget": s2}
                }
            return {
                "id": "root", "type": "split", "direction": "horizontal", "splitRatio": 25,
                "first": {"id": "n1", "type": "widget", "widget": s1},
                "second": {
                    "id": "n2", "type": "split", "direction": "vertical", "splitRatio": 66,
                    "first": {"id": "n3", "type": "widget", "widget": s2},
                    "second": {"id": "n4", "type": "widget", "widget": s3}
                }
            }

    def render_node(self, node, x, y, w, h, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode, dashboard_image, show_dividers, divider_thickness):
        if w <= 0 or h <= 0 or not node:
            return

        node_type = node.get("type", "widget")
        if node_type == "split":
            direction = node.get("direction", "horizontal")
            try:
                ratio = float(node.get("splitRatio", 50)) / 100.0
            except (ValueError, TypeError):
                ratio = 0.5
            ratio = max(0.05, min(0.95, ratio))

            first = node.get("first")
            second = node.get("second")

            if direction == "horizontal":
                w1 = int(w * ratio)
                w2 = w - w1
                self.render_node(first, x, y, w1, h, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode, dashboard_image, show_dividers, divider_thickness)
                self.render_node(second, x + w1, y, w2, h, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode, dashboard_image, show_dividers, divider_thickness)
                if show_dividers and theme_mode != 'cards':
                    draw = ImageDraw.Draw(dashboard_image)
                    draw.line([(x + w1, y), (x + w1, y + h)], fill="black", width=divider_thickness)
            else:
                h1 = int(h * ratio)
                h2 = h - h1
                self.render_node(first, x, y, w, h1, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode, dashboard_image, show_dividers, divider_thickness)
                self.render_node(second, x, y + h1, w, h2, settings, device_config, urls, colors, tz, min_hour, max_hour, font_size, theme_mode, dashboard_image, show_dividers, divider_thickness)
                if show_dividers and theme_mode != 'cards':
                    draw = ImageDraw.Draw(dashboard_image)
                    draw.line([(x, y + h1), (x + w, y + h1)], fill="black", width=divider_thickness)

        else:
            widget_type = node.get("widget", "none")
            if widget_type == "none" or not widget_type:
                return

            pad = 8 if theme_mode == 'cards' else 0
            target_w = max(1, w - 2 * pad)
            target_h = max(1, h - 2 * pad)

            widget_img = self.generate_widget_image(
                widget_type, target_w, target_h, settings, device_config,
                urls, colors, tz, min_hour, max_hour, font_size, theme_mode
            )

            if widget_img:
                if theme_mode == 'cards':
                    mask = Image.new("L", (target_w, target_h), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle((0, 0, target_w, target_h), radius=12, fill=255)
                    dashboard_image.paste(widget_img, (x + pad, y + pad), mask=mask)
                else:
                    dashboard_image.paste(widget_img, (x, y))

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
                return MultiDayCalendar({"id": "calendar"}, days=timeline_days).generate_image(cal_settings, mock_config)

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
