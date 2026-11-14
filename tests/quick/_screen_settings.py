"""兼容旧名称；所有屏幕设置已集中到config/hardware.json，旧文件见config/legacy。"""
from settings import SCREEN
PANEL = SCREEN["panel"]
SCK = SCREEN["sck"]
MOSI = SCREEN["mosi"]
CS = SCREEN["cs"]
DC = SCREEN["dc"]
RST = SCREEN["rst"]
BACKLIGHT = SCREEN["backlight"]
ROTATION = SCREEN["rotation"]
INVERT = SCREEN["invert"]
BRIGHTNESS = SCREEN["brightness"]
