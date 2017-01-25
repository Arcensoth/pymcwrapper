import abc
import threading
from queue import Queue

from pymcwrapper.event import Event


class CommandSequenceJobEvent(Event):
    def __init__(self, title: str, text: str):
        self._title = title
        self._text = text

    @property
    def title(self):
        return self._title

    @property
    def text(self):
        return self._text


class Job(abc.ABC):
    @abc.abstractmethod
    def start(self):
        """ Start the job thread. """

    @abc.abstractmethod
    def stop(self):
        """ Stop the job thread. """

    @abc.abstractmethod
    def join(self):
        """ Join with the job thread. """


class CommandSequenceJob(Job):
    def __init__(self, event_queue: Queue, title: str, delay: float, index: int, groups: list):
        super().__init__()

        self._event_queue = event_queue
        self._title = title
        self._delay = delay

        self._length = len(groups)
        self._index = index % self._length
        self._command_texts = ['\n'.join(commands) + '\n' for commands in groups]

        self._stop_event = threading.Event()

        self._thread = threading.Thread(target=self._loop_interval)

    def _loop_interval(self):
        while not self._stop_event.is_set():
            self._event_queue.put(CommandSequenceJobEvent(self._title, self._command_texts[self._index]))
            self._index = (self._index + 1) % self._length
            self._stop_event.wait(self._delay)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def join(self):
        self._thread.join()
