class Event(object):
    pass


class ExitEvent(Event):
    pass


class InputEvent(Event):
    def __init__(self, text: str):
        self._text = text

    @property
    def to_input(self):
        return self._text
