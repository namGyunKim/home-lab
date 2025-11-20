from enum import Enum, auto

# --- 상수 및 Enum 정의 ---
class ActionType(Enum):
    KEY_DOWN = 'key_down'
    KEY_UP = 'key_up'
    MOUSE_DOWN = 'mouse_down'
    MOUSE_UP = 'mouse_up'
    MOVE = 'move'

class MacroType(Enum):
    FILE = 'file'
    MEMORY = 'memory'
    IMAGE_WAIT = 'image_wait'

class RepeatMode(Enum):
    INFINITE = auto()
    COUNT = auto()
    DURATION = auto()